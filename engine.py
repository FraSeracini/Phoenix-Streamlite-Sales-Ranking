import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

PHOENIX_URL = "https://phoenix.hginsights.com/api/ai/phx_185c0d78b3d439897dc6e8cd658c2f6765b3c83a834e503e762107198bb4409b/mcp"
MAX_RESULTS = 200
CLOUD_VENDOR_ALLOWLIST = {
    "Amazon Web Services",
    "AWS",
    "Amazon",
    "Microsoft Azure",
    "Azure",
    "Google Cloud",
    "Google Cloud Platform",
    "GCP",
    "Oracle Cloud",
    "Oracle Cloud Infrastructure",
    "OCI",
    "IBM Cloud",
}


def extract_json_text(res_content):
    for block in res_content:
        if getattr(block, "type", None) == "text" and hasattr(block, "text"):
            txt = block.text.strip()
            if (txt.startswith("{") and txt.endswith("}")) or (
                txt.startswith("[") and txt.endswith("]")
            ):
                return json.loads(txt)
    raise ValueError("No JSON found in MCP response content.")


async def safe_tool_call(session, tool_name, params):
    try:
        res = await session.call_tool(tool_name, params)
        return extract_json_text(res.content)
    except Exception:
        return {}


def parse_any_date(value):
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def parse_amount(value):
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.replace("$", "").replace(",", "").strip()
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def trigger_badge(installs, contract_info=None):
    now = datetime.now(timezone.utc)

    contract_score = 0.0
    if isinstance(contract_info, dict):
        days = contract_info.get("daysToRenewal")
        if isinstance(days, int):
            if days <= 30:
                contract_score = 1.0
            elif days <= 90:
                contract_score = 0.8
            elif days <= 180:
                contract_score = 0.5
            elif days <= 365:
                contract_score = 0.2

    best_delta_days = None

    date_fields = [
        "lastVerified",
        "verificationDate",
        "lastSeen",
        "firstSeen",
        "lastUpdated",
        "lastVerifiedDate",
        "firstVerifiedDate",
    ]
    for item in installs if isinstance(installs, list) else []:
        for field in date_fields:
            date_value = parse_any_date(item.get(field)) if isinstance(item, dict) else None
            if date_value:
                delta = (now - date_value).days
                if best_delta_days is None or delta < best_delta_days:
                    best_delta_days = delta

    recency_score = 0.0
    if best_delta_days is None:
        recency_score = 0.0
    elif best_delta_days <= 30:
        recency_score = 1.0
    elif best_delta_days <= 120:
        recency_score = 0.6
    elif best_delta_days <= 365:
        recency_score = 0.2

    combined = (0.6 * contract_score) + (0.4 * recency_score)
    if combined >= 0.75:
        return "Hot"
    if combined >= 0.4:
        return "Warm"
    return "Cold"


def infer_installs(data):
    installs = data
    total_count = None
    if isinstance(data, dict):
        total_count = data.get("totalCount")
        for key in [
            "products",
            "technologies",
            "results",
            "items",
            "data",
            "installations",
            "installs",
        ]:
            if key in data and isinstance(data[key], list):
                installs = data[key]
                break
    return installs, total_count


def cloud_spend_summary(data):
    if not isinstance(data, dict):
        return {"monthlySpend": 0, "vendorCount": 0, "servicesCount": 0, "topCloudServices": []}

    services = data.get("technologyServices")
    total_spend = 0.0
    vendor_count = 0
    services_count = len(services) if isinstance(services, list) else 0

    spend_by_vendor = {}

    if isinstance(services, list):
        for service in services:
            vendors = service.get("vendors") if isinstance(service, dict) else None
            if isinstance(vendors, list):
                for vendor in vendors:
                    if not isinstance(vendor, dict):
                        continue
                    vendor_count += 1

                    vname_raw = vendor.get("vendorName") or vendor.get("name") or "Unknown"
                    vname = str(vname_raw)
                    vn = vname.lower()
                    is_cloud = any(k.lower() in vn for k in CLOUD_VENDOR_ALLOWLIST)

                    spend = vendor.get("estimatedMonthlySpend") or 0
                    if isinstance(spend, (int, float)):
                        total_spend += float(spend)
                        if is_cloud:
                            spend_by_vendor[vname] = spend_by_vendor.get(vname, 0.0) + float(spend)

    top_vendors = sorted(spend_by_vendor.items(), key=lambda x: x[1], reverse=True)[:3]
    if not top_vendors:
        top_vendors = [("Unknown cloud provider", 0.0)]

    return {
        "monthlySpend": total_spend,
        "vendorCount": vendor_count,
        "servicesCount": services_count,
        "topCloudServices": [v for v, _ in top_vendors],
    }


def spend_summary(data):
    annual_spend = 0.0
    top_categories = []
    if isinstance(data, dict):
        for key in [
            "totalSpendAmount",
            "totalSpend",
            "totalITSpendAmount",
            "totalITSpend",
            "annualSpend",
            "totalAnnualSpend",
            "itSpend",
            "totalItSpend",
        ]:
            value = parse_amount(data.get(key))
            if isinstance(value, (int, float)):
                annual_spend = max(annual_spend, float(value))

        category_lists = [
            data.get("categories"),
            data.get("categorySpend"),
            data.get("spendByCategory"),
            data.get("categoryBreakdown"),
        ]
        pairs = []
        for lst in category_lists:
            if not isinstance(lst, list):
                continue
            for item in lst:
                if not isinstance(item, dict):
                    continue
                name = (
                    item.get("category")
                    or item.get("name")
                    or item.get("categoryName")
                )
                spend = (
                    item.get("totalSpendAmount")
                    or item.get("spendAmount")
                    or item.get("totalSpend")
                    or item.get("spend")
                    or item.get("value")
                    or item.get("amount")
                )
                spend_value = parse_amount(spend)
                if name and isinstance(spend_value, (int, float)):
                    pairs.append((name, float(spend_value)))
        if pairs:
            pairs.sort(key=lambda x: x[1], reverse=True)
            top_categories = [name for name, _ in pairs[:3]]

    return {"annualSpend": annual_spend, "topCategories": top_categories}


def fai_summary(data):
    areas = []
    keywords = ["it", "engineering", "data", "security", "cloud", "ai", "machine learning", "ml"]
    if isinstance(data, dict):
        for key in ["functionalAreas", "departments", "results", "data", "items"]:
            lst = data.get(key)
            if not isinstance(lst, list):
                continue
            for item in lst:
                if not isinstance(item, dict):
                    continue
                name = (
                    item.get("name")
                    or item.get("functionalArea")
                    or item.get("department")
                    or item.get("function")
                )
                if name:
                    lowered = str(name).lower()
                    if any(keyword in lowered for keyword in keywords) and name not in areas:
                        areas.append(name)

    return {"areaCount": len(areas), "topAreas": areas[:3]}


def contract_signal(data):
    date_fields = [
        "renewalDate",
        "contractRenewalDate",
        "endDate",
        "expirationDate",
        "contractEndDate",
        "renewal",
        "renewal_date",
    ]
    candidates = []
    if isinstance(data, list):
        candidates = data
    elif isinstance(data, dict):
        for key in ["contracts", "results", "items", "data", "contractsList"]:
            lst = data.get(key)
            if isinstance(lst, list):
                candidates = lst
                break
        if not candidates:
            candidates = [data]

    dates = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        for field in date_fields:
            dt = parse_any_date(item.get(field))
            if dt:
                dates.append(dt)

    if not dates:
        return {}
    now = datetime.now(timezone.utc)
    future_dates = [dt for dt in dates if dt >= now]
    if not future_dates:
        return {}
    soonest = min(future_dates)
    days = (soonest - now).days
    return {"daysToRenewal": days}


def build_reasons(firmographic, technographic, cloud_spend, installs, spend, fai, contract_info):
    reasons = []

    if isinstance(contract_info, dict):
        days = contract_info.get("daysToRenewal")
        if isinstance(days, int) and days <= 180:
            reasons.append(f"Contract renewal window (~{days} days)")

    top_areas = (fai or {}).get("topAreas") or []
    if top_areas:
        reasons.append(f"Active in functions: {', '.join(top_areas)}")

    top_categories = (spend or {}).get("topCategories") or []
    if top_categories:
        reasons.append(f"Top IT spend areas: {', '.join(top_categories)}")

    top = technographic.get("topTechnologies") or []
    if top:
        reasons.append(f"Key stack present: {top[0]}")

    industry = firmographic.get("industry")
    if industry:
        reasons.append(f"Industry fit: {industry}")

    monthly = (cloud_spend or {}).get("monthlySpend") or 0
    if monthly:
        reasons.append(f"Cloud spend signal (~${monthly/1_000_000:.2f}M/mo)")

    annual_spend = (spend or {}).get("annualSpend") or 0
    if annual_spend:
        reasons.append(f"IT spend signal (~${annual_spend/1_000_000:.0f}M/yr)")

    badge = technographic.get("badge")
    if badge == "Hot":
        reasons.append("Recent tech verification activity (Hot)")
    elif badge == "Warm":
        reasons.append("Some recent tech activity (Warm)")

    top_vendors = (cloud_spend or {}).get("topCloudServices") or []
    if top_vendors:
        reasons.append(f"Top cloud services: {', '.join(top_vendors)}")

    return reasons[:3]


def recommended_action(technographic, cloud_spend, contract_info=None):
    badge = technographic.get("badge")
    top_vendors = (cloud_spend or {}).get("topCloudServices") or []

    if isinstance(contract_info, dict):
        days = contract_info.get("daysToRenewal")
        if isinstance(days, int) and days <= 90:
            return "Engage ahead of contract renewal window"

    if badge == "Hot":
        if top_vendors:
            return f"Outbound now with cloud services angle (focus on {top_vendors[0]})"
        return "Outbound now with recent tech change angle"

    if badge == "Warm":
        return "Prep account, monitor signals, soft outreach"

    return "Deprioritize for now"


def summarize_firmographic(data):
    if not isinstance(data, dict):
        return {}
    return {
        "name": data.get("name"),
        "industry": data.get("industry"),
        "employeeCount": data.get("employeeCount"),
        "itSpend": data.get("itSpend"),
        "country": data.get("country"),
        "website": data.get("website"),
    }


def summarize_technographic(installs, total_count=None, contract_info=None):
    summary = {
        "count": None,
        "badge": trigger_badge(installs, contract_info),
        "topTechnologies": [],
        "avgIntensity": None,
    }

    if isinstance(installs, list):
        raw_count = len(installs)
        if isinstance(total_count, int) and total_count >= raw_count:
            summary["count"] = total_count
        else:
            summary["count"] = raw_count
        intensities = []
        for item in installs[:10]:
            if isinstance(item, dict):
                name = (
                    item.get("productName")
                    or item.get("technologyName")
                    or item.get("name")
                    or item.get("vendorName")
                )
                if name:
                    summary["topTechnologies"].append(name)
                intensity = item.get("intensity")
                if isinstance(intensity, (int, float)):
                    intensities.append(float(intensity))
        if intensities:
            summary["avgIntensity"] = sum(intensities) / len(intensities)
    return summary


def fit_score(firmographic, installs, cloud_spend=None, spend=None, fai=None):
    """
    Fit score 0-100 con scale continue:
    - employees (log scale) 0-10
    - firmographic itSpend (log scale) 0-15
    - company_spend annual (log scale) 0-15
    - tech breadth 0-15
    - technographic intensity (avg) 0-15
    - cloud spend monthly (log scale) 0-20
    - functional area coverage (0-10)
    """
    employees = firmographic.get("employeeCount") or 0
    it_spend = firmographic.get("itSpend") or 0

    def log_score(value, max_points, floor=1):
        if value <= 0:
            return 0
        import math

        return min(max_points, max_points * (math.log10(value + floor) / math.log10(1_000_000_000)))

    emp_points = log_score(employees, 10)
    spend_points = log_score(it_spend, 15)

    annual_spend = 0
    if isinstance(spend, dict):
        annual_spend = spend.get("annualSpend") or 0
    spend_total_points = log_score(annual_spend, 15)

    tech_count = len(installs) if isinstance(installs, list) else 0
    tech_points = min(15, (tech_count / 50) * 15)

    intensity_points = 0
    if isinstance(installs, list) and installs:
        intensities = [item.get("intensity") for item in installs if isinstance(item, dict)]
        intensities = [v for v in intensities if isinstance(v, (int, float))]
        if intensities:
            avg_intensity = sum(intensities) / len(intensities)
            intensity_points = min(15, (avg_intensity / 2000) * 15)

    cloud_monthly = 0
    if isinstance(cloud_spend, dict):
        cloud_monthly = cloud_spend.get("monthlySpend") or 0
    cloud_points = log_score(cloud_monthly, 20)

    fai_points = 0
    if isinstance(fai, dict):
        area_count = fai.get("areaCount") or 0
        if isinstance(area_count, int):
            fai_points = min(10, area_count * 2)

    return round(
        emp_points
        + spend_points
        + spend_total_points
        + tech_points
        + intensity_points
        + cloud_points
        + fai_points,
        2,
    )


def final_score(fit, badge):
    """
    Trigger come boost (timing).
    """
    boost = 0
    if badge == "Hot":
        boost = 15
    elif badge == "Warm":
        boost = 7
    return fit + boost


async def fetch_domain_summary(session, domain):
    firmographic_res = await session.call_tool("company_firmographic", {"companyDomain": domain})
    firmographic_data = extract_json_text(firmographic_res.content)

    technographic_res = await session.call_tool(
        "company_technographic",
        {"companyDomain": domain, "limit": MAX_RESULTS, "maxResults": MAX_RESULTS},
    )
    technographic_data = extract_json_text(technographic_res.content)

    cloud_spend_res = await session.call_tool("company_cloud_spend", {"companyDomain": domain})
    cloud_spend_data = extract_json_text(cloud_spend_res.content)
    cloud_spend = cloud_spend_summary(cloud_spend_data)

    spend_data = await safe_tool_call(session, "company_spend", {"companyDomain": domain})
    spend = spend_summary(spend_data)

    contracts_data = await safe_tool_call(
        session, "company_contracts", {"companyDomain": domain}
    )
    contract_info = contract_signal(contracts_data)

    out_dir = Path("out")
    out_dir.mkdir(exist_ok=True)
    (out_dir / f"{domain}_firmographic.json").write_text(
        json.dumps(firmographic_data, indent=2), encoding="utf-8"
    )
    (out_dir / f"{domain}_technographic.json").write_text(
        json.dumps(technographic_data, indent=2), encoding="utf-8"
    )
    (out_dir / f"{domain}_spend.json").write_text(
        json.dumps(spend_data, indent=2), encoding="utf-8"
    )
    installs, total_count = infer_installs(technographic_data)

    top_products = []
    if isinstance(installs, list):
        for item in installs:
            if not isinstance(item, dict):
                continue
            name = (
                item.get("productName")
                or item.get("technologyName")
                or item.get("name")
            )
            if name and name not in top_products:
                top_products.append(name)
            if len(top_products) >= 3:
                break

    fai_data = {}
    if top_products:
        fai_data = await safe_tool_call(
            session, "company_fai", {"companyDomain": domain, "products": top_products}
        )
    fai = fai_summary(fai_data)

    (out_dir / f"{domain}_cloud_spend.json").write_text(
        json.dumps(cloud_spend_data, indent=2), encoding="utf-8"
    )
    (out_dir / f"{domain}_fai.json").write_text(
        json.dumps(fai_data, indent=2), encoding="utf-8"
    )
    (out_dir / f"{domain}_contracts.json").write_text(
        json.dumps(contracts_data, indent=2), encoding="utf-8"
    )

    return (
        summarize_firmographic(firmographic_data),
        summarize_technographic(installs, total_count, contract_info),
        installs,
        cloud_spend,
        spend,
        fai,
        contract_info,
    )


async def prioritize_accounts(domains: list[str]) -> list[dict]:
    async with streamable_http_client(PHOENIX_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            def build_result(domain, firmographic, technographic, installs, cloud_spend, spend, fai, contract_info):
                fit = fit_score(firmographic, installs, cloud_spend, spend, fai)
                badge = technographic.get("badge")
                final = final_score(fit, badge)

                days_to_renewal = None
                if isinstance(contract_info, dict):
                    days_to_renewal = contract_info.get("daysToRenewal")

                return {
                    "domain": domain,
                    "company": firmographic.get("name"),
                    "score": round(final, 2),
                    "badge": badge,
                    "employeeCount": firmographic.get("employeeCount"),
                    "itSpend": firmographic.get("itSpend"),
                    "companySpendAnnual": (spend or {}).get("annualSpend"),
                    "techCount": technographic.get("count"),
                    "techIntensity": technographic.get("avgIntensity"),
                    "cloudMonthlySpend": (cloud_spend or {}).get("monthlySpend"),
                    "cloudTopServices": (cloud_spend or {}).get("topCloudServices"),
                    "faiAreas": (fai or {}).get("topAreas"),
                    "spendTopCategories": (spend or {}).get("topCategories"),
                    "industry": firmographic.get("industry"),
                    "topTechnologies": technographic.get("topTechnologies"),
                    "daysToRenewal": days_to_renewal,
                    "reasons": build_reasons(
                        firmographic, technographic, cloud_spend, installs, spend, fai, contract_info
                    ),
                    "action": recommended_action(technographic, cloud_spend, contract_info),
                }

            clean = []
            for domain in domains:
                last_exc = None
                for attempt in range(2):
                    try:
                        firmographic, technographic, installs, cloud_spend, spend, fai, contract_info = (
                            await fetch_domain_summary(session, domain)
                        )
                        clean.append(
                            build_result(
                                domain, firmographic, technographic, installs, cloud_spend, spend, fai, contract_info
                            )
                        )
                        last_exc = None
                        break
                    except Exception as exc:
                        last_exc = exc
                        await asyncio.sleep(0.5 * (attempt + 1))
                if last_exc is not None:
                    continue

    return sorted(clean, key=lambda x: x["score"], reverse=True)