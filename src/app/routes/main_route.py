import math
from typing import List

from flask import Blueprint, render_template, request
from flask_login import current_user, login_required
from src.repository.PLC_repository import Plcrepo
from src.utils import role_required
from src.utils.tags import parse_tags
from src.services.security.industrial_security import assess_plc_security

main = Blueprint('main', __name__)


def _build_clp_view(plc) -> dict:
    tags = plc.tags_as_list()
    security = assess_plc_security(plc)
    level_slug = security.level.lower().replace('í', 'i')

    return {
        "id": plc.id,
        "name": plc.name,
        "ip_address": plc.ip_address,
        "protocol": plc.protocol,
        "is_online": plc.is_online,
        "tags": tags,
        "security": {
            "score": security.score,
            "level": security.level,
            "level_slug": level_slug,
        },
    }




# @role_required("user")
@main.route('/', methods=['GET', 'POST'])
@login_required
def index():
    search_term = (request.args.get('q') or '').strip()
    tag_query = (request.args.get('tags') or '').strip()
    page = max(int(request.args.get('page', 1) or 1), 1)
    per_page = request.args.get('per_page', 12)
    try:
        per_page = max(1, min(int(per_page), 48))
    except (TypeError, ValueError):
        per_page = 12

    requested_tags = parse_tags(tag_query)

    all_plcs = Plcrepo.list_all()
    all_tags = set()
    filtered: List[dict] = []
    for plc in all_plcs:
        tags = plc.tags_as_list()
        all_tags.update(tags)

        if search_term:
            search_lower = search_term.lower()
            if search_lower not in (plc.name or '').lower() and search_lower not in (plc.ip_address or '').lower():
                continue

        if requested_tags and not all(tag in tags for tag in requested_tags):
            continue

        filtered.append(_build_clp_view(plc))

    total_items = len(filtered)
    total_pages = max(1, math.ceil(total_items / per_page))
    page = min(page, total_pages)
    start = (page - 1) * per_page
    end = start + per_page
    paginated = filtered[start:end]

    pagination = {
        "page": page,
        "per_page": per_page,
        "total_items": total_items,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_page": page - 1,
        "next_page": page + 1,
    }

    return render_template(
        "index/index.html",
        clps=paginated,
        pagination=pagination,
        search_term=search_term,
        selected_tags=requested_tags,
        available_tags=sorted(all_tags),
        raw_tag_query=tag_query,
    )


