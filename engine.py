import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

PHOENIX_URL = "https://phoenix.hginsights.com/api/ai/phx_185c0d78b3d439897dc6e8cd658c2f6765b3c83a834e503e762107198bb4409b/mcp"
MAX_RESULTS = 50
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


def parse_any_date(value):
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def trigger_badge(installs):
    now = datetime.now(timezone.utc)
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

    if best_delta_days is None:
        return "Cold"
    if best_delta_days <= 30:
        return "Hot"
    if best_delta_days <= 120:
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


def build_reasons(firmographic, technographic, cloud_spend, installs):
    reasons = []

    monthly = (cloud_spend or {}).get("monthlySpend") or 0
    if monthly:
        reasons.append(f"Cloud spend signal (~${monthly/1_000_000:.2f}M/mo)")

    top_vendors = (cloud_spend or {}).get("topCloudServices") or []
    if top_vendors:
        reasons.append(f"Top cloud services: {', '.join(top_vendors)}")

    it_spend = firmographic.get("itSpend") or 0
    if it_spend:
        reasons.append(f"High IT spend (~${it_spend/1_000_000:.0f}M/yr)")

    badge = technographic.get("badge")
    if badge == "Hot":
        reasons.append("Recent tech verification activity (Hot)")
    elif badge == "Warm":
        reasons.append("Some recent tech activity (Warm)")

    top = technographic.get("topTechnologies") or []
    if top:
        reasons.append(f"Key stack present: {top[0]}")

    return reasons[:2]


def recommended_action(technographic, cloud_spend):
    badge = technographic.get("badge")
    top_vendors = (cloud_spend or {}).get("topCloudServices") or []

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


def summarize_technographic(installs, total_count=None):
    summary = {
        "count": total_count if isinstance(total_count, int) else (len(installs) if isinstance(installs, list) else None),
        "badge": trigger_badge(installs),
        "topTechnologies": [],
    }

    if isinstance(installs, list):
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
    return summary


def fit_score(firmographic, installs, cloud_spend=None):
    """
    Fit score 0-100 con scale continue:
    - employees (log scale) 0-25
    - itSpend (log scale) 0-25
    - tech breadth 0-20
    - technographic intensity (avg) 0-15
    - cloud spend monthly (log scale) 0-15
    """
    employees = firmographic.get("employeeCount") or 0
    it_spend = firmographic.get("itSpend") or 0

    def log_score(value, max_points, floor=1):
        if value <= 0:
            return 0
        import math

        return min(max_points, max_points * (math.log10(value + floor) / math.log10(1_000_000_000)))

    emp_points = log_score(employees, 25)
    spend_points = log_score(it_spend, 25)

    tech_count = len(installs) if isinstance(installs, list) else 0
    tech_points = min(20, (tech_count / 50) * 20)

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
    cloud_points = log_score(cloud_monthly, 15)

    return round(emp_points + spend_points + tech_points + intensity_points + cloud_points, 2)


def final_score(fit, badge):
    """
    Trigger come boost (timing).
    """
    boost = 0
    if badge == "Hot":
        boost = 20
    elif badge == "Warm":
        boost = 10
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

    out_dir = Path("out")
    out_dir.mkdir(exist_ok=True)
    (out_dir / f"{domain}_firmographic.json").write_text(
        json.dumps(firmographic_data, indent=2), encoding="utf-8"
    )
    (out_dir / f"{domain}_technographic.json").write_text(
        json.dumps(technographic_data, indent=2), encoding="utf-8"
    )
    (out_dir / f"{domain}_cloud_spend.json").write_text(
        json.dumps(cloud_spend_data, indent=2), encoding="utf-8"
    )

    installs, total_count = infer_installs(technographic_data)
    return (
        summarize_firmographic(firmographic_data),
        summarize_technographic(installs, total_count),
        installs,
        cloud_spend,
    )


async def prioritize_accounts(domains: list[str]) -> list[dict]:
    async with streamable_http_client(PHOENIX_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            def build_result(domain, firmographic, technographic, installs, cloud_spend):
                fit = fit_score(firmographic, installs, cloud_spend)
                badge = technographic.get("badge")
                final = final_score(fit, badge)

                return {
                    "domain": domain,
                    "company": firmographic.get("name"),
                    "score": round(final, 2),
                    "badge": badge,
                    "reasons": build_reasons(
                        firmographic, technographic, cloud_spend, installs
                    ),
                    "action": recommended_action(technographic, cloud_spend),
                }

            clean = []
            for domain in domains:
                last_exc = None
                for attempt in range(2):
                    try:
                        firmographic, technographic, installs, cloud_spend = (
                            await fetch_domain_summary(session, domain)
                        )
                        clean.append(
                            build_result(domain, firmographic, technographic, installs, cloud_spend)
                        )
                        last_exc = None
                        break
                    except Exception as exc:
                        last_exc = exc
                        await asyncio.sleep(0.5 * (attempt + 1))
                if last_exc is not None:
                    continue

    return sorted(clean, key=lambda x: x["score"], reverse=True)