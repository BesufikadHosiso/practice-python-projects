"""Deterministic demo data so the console is useful the second it boots.

Run it with ``python -m app.seed`` (add ``--fresh`` to wipe the database first).
The generator is seeded, so every fresh workspace looks identical — which makes
screenshots and manual QA reproducible.
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone

from . import config, database as db, security, services

SEED = 20260908

# --------------------------------------------------------------------- blueprints
GROUP_BLUEPRINTS = [
    {
        "name": "Remote Dev Jobs Worldwide",
        "handle": "remote-dev-jobs",
        "category": "Careers",
        "privacy": "public",
        "members": 128_430,
        "daily_posts": 74,
        "moderation": "keyword_filter",
        "description": "Vetted remote engineering, design and product roles. No recruiters, no crypto.",
    },
    {
        "name": "Vintage Camera Collectors",
        "handle": "vintage-camera-collectors",
        "category": "Hobby",
        "privacy": "private",
        "members": 34_211,
        "daily_posts": 41,
        "moderation": "post_approval",
        "description": "Film bodies, lenses, repairs and fair-priced trades. Scammers get banned fast.",
    },
    {
        "name": "Bay Area Foodies",
        "handle": "bay-area-foodies",
        "category": "Food & Drink",
        "privacy": "public",
        "members": 87_905,
        "daily_posts": 63,
        "moderation": "post_approval",
        "description": "SF / Oakland / San Jose restaurants, openings and honest reviews.",
    },
    {
        "name": "Python Developers Hub",
        "handle": "python-developers-hub",
        "category": "Technology",
        "privacy": "public",
        "members": 214_672,
        "daily_posts": 118,
        "moderation": "keyword_filter",
        "description": "Help, code review and release chatter. Course spam and DM-solicitation removed daily.",
    },
    {
        "name": "Plant Parents Society",
        "handle": "plant-parents-society",
        "category": "Home & Garden",
        "privacy": "private",
        "members": 56_120,
        "daily_posts": 52,
        "moderation": "post_approval",
        "description": "Rare aroids, pest rescue, propagation swaps. Local pickup preferred.",
    },
    {
        "name": "DIY Home Renovation Crew",
        "handle": "diy-home-renovation",
        "category": "Home Improvement",
        "privacy": "private",
        "members": 42_877,
        "daily_posts": 38,
        "moderation": "admin_only",
        "description": "Before/after builds, tool talk and 'is this load bearing?' questions.",
    },
]

MEMBER_NAMES = [
    "Marisol Vega", "Tobias Lindqvist", "Priya Raghunathan", "Deshawn Carter", "Hana Yamamoto",
    "Lukas Brenner", "Aoife Mulcahy", "Mateo Ferreira", "Nadia Haddad", "Colin Whitfield",
    "Sofia Marchetti", "Emeka Nwosu", "Greta Halvorsen", "Rafael Ortega", "Yuki Tanabe",
    "Ingrid Sørensen", "Dev Patel", "Camille Rousseau", "Omar El-Sayed", "Beatrice Kimani",
    "Tomasz Wójcik", "Leah Bergström", "Andrei Popescu", "Nia Thompson", "Felix Adeyemi",
    "Rosa Delgado", "Kwame Mensah", "Elin Jónsdóttir", "Marcus Boyle", "Sana Qureshi",
    "Hiroshi Nakamura", "Valentina Cruz", "Seán Ó Donnghaile", "Amara Diallo", "Jonas Feld",
    "Talia Ben-Ari", "Connor McGee", "Zainab Osman", "Petr Novák", "Lucia Moretti",
    "Ravi Chandran", "Freya Lindholm", "Diego Salazar", "Mei-Ling Chen", "Bogdan Ionescu",
]

# Members who only ever show up to spam the groups.
SPAMMER_NAMES = [
    "Crypto King 24", "Fast Cash Lola", "DropShip Winner", "Naira Forex Hub", "Blessed Trader",
    "Quick Loans Mike", "SEO Boost Pro", "Gift Card Deals", "Alpha Signals Bot", "Viral Growth Lab",
]

LEGIT_POSTS: dict[str, list[str]] = {
    "Careers": [
        "We're hiring a senior backend engineer (Python/Django), fully remote, EU timezones ±3h. Salary band 70–95k EUR. Link in the comments.",
        "After 4 years remote I finally negotiated a 4-day week. Happy to walk through the exact proposal doc if anyone wants it.",
        "Reminder that 'remote-friendly' and 'remote-first' are not the same thing. Ask about the overlap hours before you sign.",
        "Hiring manager here: we read every cover letter that mentions a real tradeoff you made. The template ones get skimmed.",
        "Anyone else getting ghosted after 5 rounds? Sharing my spreadsheet of companies that actually responded within 2 weeks.",
        "Took a contract role at 60% of my old salary for 6 months of flexibility. No regrets, but budget hard first.",
    ],
    "Hobby": [
        "Picked up a 1962 Pentax SV with the original 55mm f/1.8. Light seals need replacing but the glass is spotless.",
        "Does anyone have a spare advance lever for a Zenit-E? Happy to cover shipping both ways.",
        "Developed my first roll of Tri-X at home last night. The kitchen sink method is honestly not scary once you've done it twice.",
        "PSA: those 'new old stock' Rolleiflex listings on the marketplace are re-sealed fakes. Check the hinge wear.",
        "Traded a Yashica Mat for a box of expired Portra. Both of us are happy, which is the whole point of this group.",
        "Meter calibration question — my Sekonic reads a full stop hot against my phone's incident dome. Which one do I trust?",
    ],
    "Food & Drink": [
        "The new ramen spot on Irving has a 2-hour weekend wait. Went at 2pm Tuesday and got a seat in 20 minutes. Tonkotsu is worth it.",
        "Unpopular opinion: the Mission burrito peaked in 2011 and the rice-to-bean ratio has been sliding ever since.",
        "Opened a pop-up in a Oakland parking lot last Friday and sold out of 180 plates in 3 hours. Ask me anything about permits.",
        "Finally found a decent banh mi in the South Bay that doesn't drown the bread in mayo. Parking is awful though.",
        "Home bakers: my sourdough keeps spreading instead of rising. 78% hydration, 4-hour bulk at 24°C. What am I missing?",
        "Coffee crawl notes from the weekend — 6 shops, 2 worth the drive, one that served me a flat white with visible bubbles.",
    ],
    "Technology": [
        "PSA: datetime.utcnow() returns a naive datetime and will bite you at the first timezone conversion. Use datetime.now(timezone.utc).",
        "Spent the weekend migrating a 40k-line codebase from mypy to pyright. Net result: 300 fewer ignores, 12 real bugs found.",
        "Hot take: most Python services don't need async. Your bottleneck is the database, not the event loop.",
        "Released v0.9 of my little SQLite-backed task runner. 400 lines, no deps, handles 50k jobs/day on a $5 VPS.",
        "If your CI takes 40 minutes, start by caching the dependency resolution step. Cut ours from 38 to 11 minutes.",
        "Reading the FastAPI dependency docs properly for the first time and I've been hand-rolling auth for three years. Ouch.",
    ],
    "Home & Garden": [
        "My monstera finally fenestrated after 18 months of an east-facing window and monthly feed. Patience genuinely wins.",
        "Spider mite rescue update: week 3 of neem + weekly shower and the new growth is clean. Photos in comments.",
        "Stop repotting into a much bigger pot 'so it has room'. Two sizes up maximum or you're just inviting root rot.",
        "Propagated 40 pothos cuttings in water over the winter. 38 rooted. The two failures were the ones I forgot about.",
        "Local swap this Saturday at the community garden — bringing a rooted philodendron birkin and a sad-but-alive fiddle leaf.",
        "West-facing window is cooking my calathea. Moved it 1m back and added a sheer curtain; crisping stopped within a week.",
    ],
    "Home Improvement": [
        "Regrouted the bathroom floor in a weekend with a $14 float. Biggest lesson: seal the grout before it fully cures, not after.",
        "Is this load bearing? 1920s bungalow, removing a 6ft section between kitchen and dining. Photos attached.",
        "Rented a drum sander for the first time. Went 60 → 120 → 180 grit and the oak looks better than the original install.",
        "Total cost of our kitchen refresh: $4,180 and 6 weekends. Breakdown with links in the comments, no affiliate nonsense.",
        "PSA about the cheap quartz slabs at the big box store — the veining is printed and it shows under side lighting.",
        "Finished the garage insulation project. R-19 batts, taped seams, and the room went from 34°C to 26°C in August.",
    ],
}

PENDING_QUESTIONS = [
    "First post here — is it okay to share a link to my portfolio, or does that count as self-promotion?",
    "Mods: can we get a weekly thread for this? The same question comes up about twice a day.",
    "Selling my gear locally, pickup only. Is that allowed or should this go in the marketplace group?",
    "Not sure if this is the right place but has anyone dealt with a scam buyer from this group?",
    "Reposting because my first post got removed — was it the link? Happy to edit it out.",
    "Quick question, does anyone have experience with the newer version of this? Considering the upgrade.",
    "Sorry if this is off-topic but can someone point me to the pinned rules? I can't find them on mobile.",
]

SPAM_POSTS = [
    "🔥 WORK FROM HOME $500 DAILY! DM me 'WORK' for details. No experience needed! https://bit.ly/easy-cash-now",
    "SELL CHEAP CAMERA EQUIPMENT!! WhatsApp +628123456789 for the full price list. Canon Sony Nikon 100% original",
    "FREE FOOD DELIVERY PROMO CODE: EATFREE99 — valid today only. Download now https://tinyurl.com/free-food-promo",
    "Learn Python in 7 days and earn $3000/month GUARANTEED. Join my Telegram group, link in bio 📈",
    "Rare variegated monstera albo cutting $299!!! DM me to reserve, only 3 left, ships worldwide 🌱🌱🌱",
    "CHEAP CONTRACTOR SERVICES — full kitchen remodel from $999! Call me now +1 (555) 019-2834 lowest price guaranteed",
    "Crypto signal group made 340% last month 🚀 DM 'ALPHA' and I'll add you. Not financial advice lol",
    "Need cash fast? Instant approval loans up to $25,000, no credit check. Apply here https://quickcash-approve.xyz",
    "Tag 3 friends to WIN a free iPhone 18 Pro Max! Winner announced Friday. Must be following to enter 👇👇",
    "I was $12,000 in debt until I found this one trick. Inbox me and I'll share it for free, serious people only",
    "FOREX MENTORSHIP 💰 $99 lifetime access, 92% win rate. WhatsApp me +447700900123 to start today",
    "http://totally-legit-store.shop — brand new Nikon Z8 for $410, only 2 in stock, ships from warehouse",
]

SPAM_DUPLICATE = "DM me for details — serious inquiries only, no time wasters 🙏"


def _dt(rng: random.Random, days_ago: int) -> str:
    now = datetime.now(timezone.utc)
    moment = now - timedelta(days=days_ago, hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
    return moment.replace(microsecond=0).isoformat()


def _pick_author(rng: random.Random, owner_id: int, group_id: int, spammy: bool) -> dict:
    pool = SPAMMER_NAMES if spammy else MEMBER_NAMES
    name = rng.choice(pool)
    row = db.query_one(
        "SELECT * FROM authors WHERE owner_id = ? AND lower(name) = lower(?)", (owner_id, name)
    )
    if row:
        return row
    author_id = db.execute(
        """INSERT INTO authors (owner_id, group_id, name, handle, avatar_seed, joined_at,
                                is_banned, risk_score, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            owner_id, group_id, name,
            "@" + services.slugify(name), services.db_initials(name),
            _dt(rng, rng.randint(40, 900)),
            int(spammy and rng.random() < 0.35),
            rng.randint(72, 99) if spammy else rng.randint(0, 34),
            db.utcnow(),
        ),
    )
    return db.query_one("SELECT * FROM authors WHERE id = ?", (author_id,))


def make_random_post(rng: random.Random, owner_id: int, group: dict) -> dict:
    """Build (and persist) one believable new post — also used by /groups/{id}/sync."""
    category = group.get("category", "Community")
    spammy = rng.random() < 0.45
    author = _pick_author(rng, owner_id, group["id"], spammy)
    post_type = rng.choices(
        ["text", "photo", "link", "video", "poll", "live", "event"],
        weights=[46, 22, 14, 8, 5, 3, 2],
    )[0]
    if spammy:
        message = rng.choice(SPAM_POSTS)
        state = rng.choices(["pending", "flagged", "published"], weights=[45, 25, 30])[0]
        likes, comments, shares = rng.randint(0, 3), rng.randint(0, 2), rng.randint(0, 1)
        reports = rng.randint(1, 9) if state == "flagged" else rng.randint(0, 1)
        reason = {
            "pending": "Awaiting moderator approval",
            "flagged": "Reported by members",
            "published": "",
        }[state]
    else:
        pool = LEGIT_POSTS.get(category) or LEGIT_POSTS["Technology"]
        message = rng.choice(pool + PENDING_QUESTIONS)
        state = rng.choices(["published", "pending", "flagged"], weights=[70, 22, 8])[0]
        likes = rng.randint(2, 240)
        comments = rng.randint(0, 46)
        shares = rng.randint(0, 18)
        reports = rng.randint(1, 3) if state == "flagged" else 0
        reason = "Awaiting moderator approval" if state == "pending" else (
            "Reported by members" if state == "flagged" else ""
        )

    now = db.utcnow()
    post_id = db.execute(
        """INSERT INTO posts (owner_id, group_id, author_id, author_name, message, post_type, state,
                              likes, comments, shares, reports, reason, published_at,
                              created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            owner_id, group["id"], author["id"], author["name"], message, post_type, state,
            likes, comments, shares, reports, reason,
            now if state == "published" else None, now, now,
        ),
    )
    return {
        "id": post_id, "author_id": author["id"], "author_name": author["name"],
        "message": message, "post_type": post_type, "state": state, "likes": likes,
        "comments": comments, "shares": shares, "reports": reports,
        "published_at": now if state == "published" else None, "created_at": now,
    }


def _seed_posts(rng: random.Random, owner_id: int, group: dict) -> None:
    """Spread ~30 posts per group across the last 45 days."""
    category = group.get("category", "Technology")
    legit_pool = LEGIT_POSTS.get(category, LEGIT_POSTS["Technology"])
    volume = rng.randint(26, 38)

    for index in range(volume):
        days_ago = rng.randint(0, 45)
        created = _dt(rng, days_ago)
        spammy = rng.random() < 0.42
        author = _pick_author(rng, owner_id, group["id"], spammy)
        post_type = rng.choices(
            ["text", "photo", "link", "video", "poll", "live", "event"],
            weights=[46, 22, 14, 8, 5, 3, 2],
        )[0]

        roll = rng.random()
        if roll < 0.14:
            state, deleted = "pending", None
            message = rng.choice(SPAM_POSTS) if spammy else rng.choice(PENDING_QUESTIONS)
            reason = "Awaiting moderator approval"
            likes, comments, shares, reports = 0, rng.randint(0, 2), 0, 0
        elif roll < 0.24:
            state, deleted = "flagged", None
            message = rng.choice(SPAM_POSTS) if spammy else rng.choice(legit_pool)
            reason = rng.choice([
                "Reported by 3 members", "Possible scam — reported",
                "Off-topic, reported", "Contains external link",
            ])
            likes, comments, shares = rng.randint(0, 22), rng.randint(0, 12), rng.randint(0, 4)
            reports = rng.randint(1, 11)
        elif roll < 0.31:
            state, deleted = "scheduled", None
            message = rng.choice(legit_pool)
            reason = "Scheduled by admin"
            likes, comments, shares, reports = 0, 0, 0, 0
        elif roll < 0.86:
            state, deleted = "published", None
            message = rng.choice(legit_pool + PENDING_QUESTIONS)
            reason = ""
            likes, comments, shares = rng.randint(4, 260), rng.randint(0, 48), rng.randint(0, 21)
            reports = 0
        else:
            # Already cleaned up: sitting in the trash, or purged by an old sweep.
            state, deleted = rng.choice(["pending", "flagged", "published"]), _dt(rng, max(0, days_ago - 1))
            message = rng.choice(SPAM_POSTS if spammy else legit_pool)
            reason = rng.choice([
                "Duplicate of an earlier post", "External link to a shortened URL",
                "Reported by members", "Banned keyword: guaranteed income",
                "Declined by moderator",
            ])
            likes, comments, shares = rng.randint(0, 8), rng.randint(0, 4), 0
            reports = rng.randint(0, 6)

        if spammy and rng.random() < 0.18:
            message = SPAM_DUPLICATE  # exercises the duplicate rule

        scheduled_for = _dt(rng, -rng.randint(1, 9)) if state == "scheduled" else None
        db.execute(
            """INSERT INTO posts (owner_id, group_id, author_id, author_name, message, post_type,
                                  state, likes, comments, shares, reports, reason, prior_state,
                                  scheduled_for, published_at, created_at, updated_at, deleted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                owner_id, group["id"], author["id"], author["name"], message, post_type, state,
                likes, comments, shares, reports, reason,
                state if deleted else None, scheduled_for,
                created if state == "published" else None, created, created, deleted,
            ),
        )


RULE_BLUEPRINTS = [
    ("Remove crypto & forex spam", "Anything pitching a trading group, signal service or 'guaranteed' return.",
     None, "keyword", "crypto, forex, signal, guaranteed return", 0, "delete", "high"),
    ("Block DM / inbox solicitation", "\"DM me\", \"inbox me\" and \"WhatsApp me\" are how the bots funnel people out.",
     None, "keyword", "dm me, inbox me, whatsapp", 0, "delete", "high"),
    ("Strip shortened URL spam", "Posts linking to bit.ly / tinyurl / t.co are almost never legitimate here.",
     None, "domain", "bit.ly,tinyurl.com,t.co,wa.me", 0, "flag", "medium"),
    ("Delete reported posts", "Once 3+ members report a post, take it down and let the author appeal.",
     None, "reported", "", 3, "delete", "high"),
    ("Prune zero-engagement posts", "Posts with no reactions after a week are usually drive-by advertising.",
     None, "low_engagement", "", 0, "flag", "low"),
    ("Archive posts older than 90 days", "Keeps the group searchable without nuking history.",
     None, "age_days", "", 90, "archive", "low"),
    ("Repeat poster guard", "Members posting 4+ times a day are usually farming reach.",
     None, "repeat_poster", "", 4, "flag", "medium"),
    ("Sweep banned members", "Any live post from an author already banned in another group.",
     None, "banned_author", "", 0, "delete", "high"),
    ("Collapse duplicate posts", "Same message posted repeatedly within a short window.",
     None, "duplicate", "", 0, "delete", "medium"),
]


def _seed_rules(owner_id: int, group_ids: list[int]) -> None:
    for index, (name, description, _group, condition, value, threshold, action, severity) in enumerate(
        RULE_BLUEPRINTS
    ):
        group_id = group_ids[index % 3] if index in (4, 6) else None
        rng = random.Random(SEED + index)
        runs = rng.randint(2, 24)
        affected = rng.randint(4, 60)
        db.execute(
            """INSERT INTO rules (owner_id, group_id, name, description, condition_type,
                                  condition_value, threshold, action, severity, enabled, runs,
                                  affected, last_run_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                owner_id, group_id, name, description, condition, value, threshold, action,
                severity, int(index not in (4, 6)), runs, affected,
                _dt(rng, rng.randint(0, 6)), _dt(rng, rng.randint(10, 40)),
            ),
        )


def _seed_jobs(owner_id: int) -> None:
    rng = random.Random(SEED + 99)
    jobs = [
        ("Nightly spam sweep", "delete", False, "completed", rng.randint(18, 40)),
        ("Pending queue older than 7 days", "delete", False, "completed", rng.randint(6, 22)),
        ("Duplicate post collapse", "delete", False, "completed", rng.randint(3, 14)),
        ("Weekend preview run", "delete", True, "completed", rng.randint(20, 55)),
        ("Zero-engagement archive", "flag", False, "completed", rng.randint(9, 31)),
    ]
    for name, action, dry_run, status_text, matched in jobs:
        db.execute(
            """INSERT INTO clean_jobs (owner_id, name, group_ids, filters, action, dry_run, status,
                                       matched, processed, duration_ms, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                owner_id, name, db.dump_json([]),
                db.dump_json({"older_than_days": 7, "contains_link": True}),
                action, int(dry_run), status_text, matched,
                0 if dry_run else matched, rng.randint(120, 900), _dt(rng, rng.randint(0, 12)),
            ),
        )


def _seed_history(owner_id: int, owner_name: str) -> None:
    rng = random.Random(SEED + 7)
    groups = db.query("SELECT id, name FROM groups WHERE owner_id = ?", (owner_id,))
    events = [
        ("group.connected", "group", "Connected {group}", "Imported 90 days of history"),
        ("rule.created", "rule", "Remove crypto & forex spam", "Trigger: keyword"),
        ("post.deleted", "post", "12 posts", "Duplicate of an earlier post"),
        ("post.approved", "post", "8 posts", "Approved from the pending queue"),
        ("rule.ran", "rule", "Strip shortened URL spam", "23 post(s) flagged by rule"),
        ("clean.job", "job", "Nightly spam sweep", "31 post(s) deleted across 6 group(s)"),
        ("author.updated", "author", "Crypto King 24", "Banned from all groups"),
        ("post.declined", "post", "5 posts", "Declined by moderator"),
        ("group.synced", "group", "Synced {group}", "Pulled 18 new post(s) from Facebook"),
        ("post.restored", "post", "1 post", "Restored from trash after an appeal"),
    ]
    for index in range(28):
        action, target_type, label, detail = events[index % len(events)]
        group = rng.choice(groups)
        created = _dt(rng, index // 2)
        db.execute(
            """INSERT INTO activity (owner_id, actor, action, target_type, target_id, target_label,
                                     group_id, detail, created_at)
               VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?)""",
            (
                owner_id, owner_name, action, target_type,
                label.replace("{group}", group["name"]), group["id"], detail, created,
            ),
        )


GUARANTEED_SPAM: tuple[tuple[str, str, str, int, int, int], ...] = (
    # (message, post_type, state, likes, comments, reports)
    ("Crypto signal group made 340% last month 🚀 DM 'ALPHA' and I'll add you. Not financial advice lol", "link", "published", 1, 0, 2),
    ("FOREX MENTORSHIP 💰 $99 lifetime access, 92% win rate. WhatsApp me +447700900123 to start today", "text", "pending", 0, 0, 0),
    ("Bitcoin and USDT arbitrage bot, guaranteed 8% weekly. Inbox me 'BOT' for the private group link", "link", "flagged", 0, 1, 4),
    ("NFT whitelist giveaway + crypto airdrop — first 50 only. Join https://t.me/airdrop-alpha now", "link", "published", 3, 1, 1),
    ("DM me for details — serious inquiries only, no time wasters 🙏", "text", "published", 0, 0, 0),
    ("Inbox me 'READY' and I'll send the full breakdown. Don't comment here, they delete fast", "text", "pending", 0, 0, 0),
    ("WhatsApp me on +6281234567890 for the price list, I don't check this app", "text", "published", 1, 0, 1),
    ("Brand new kit for half price — https://bit.ly/2x-cheap-gear only 2 left", "link", "published", 0, 0, 1),
    ("Full menu attached https://tinyurl.com/menu-deals — order before midnight", "link", "flagged", 2, 0, 3),
    ("Tutorial is here https://t.co/x9f2abc limited time free access", "link", "pending", 0, 0, 0),
    ("Selling my whole setup, moving abroad. Reports from last time were fake, please don't report again", "photo", "flagged", 4, 2, 5),
    ("This is definitely not a scam, trust me. 12 people already reported me unfairly", "text", "flagged", 1, 3, 6),
    ("Reported three times already but I'll repost until someone answers: who sells these?", "text", "flagged", 0, 4, 3),
    ("Anyone? Anyone at all? Bueller?", "text", "published", 0, 0, 0),
    ("bump", "text", "published", 0, 0, 0),
    ("following for updates", "text", "published", 0, 0, 0),
    ("DM me for details — serious inquiries only, no time wasters 🙏", "text", "published", 0, 0, 0),
    ("DM me for details — serious inquiries only, no time wasters 🙏", "text", "published", 1, 0, 0),
)


def _seed_guaranteed_spam(rng: random.Random, owner_id: int, group_ids: list[int]) -> None:
    """Seed a fixed block of spam so every shipped rule matches on first load.

    The randomised posts above are good for texture, but with a small corpus the
    long-tail patterns (crypto, forex, shortened URLs) can randomly vanish, and
    a pre-built rule that matches nothing looks broken. These rows are always
    live and always recent.
    """
    for index, (message, post_type, state, likes, comments, reports) in enumerate(GUARANTEED_SPAM):
        group_id = group_ids[index % len(group_ids)]
        created = _dt(rng, index % 21)
        author = _pick_author(rng, owner_id, group_id, spammy=True)
        reason = {
            "pending": "Awaiting moderator approval",
            "flagged": f"Reported by {reports} members",
            "published": "",
        }[state]
        db.execute(
            """INSERT INTO posts (owner_id, group_id, author_id, author_name, message, post_type,
                                  state, likes, comments, shares, reports, reason, published_at,
                                  created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                owner_id, group_id, author["id"], author["name"], message, post_type, state,
                likes, comments, rng.randint(0, 1), reports, reason,
                created if state == "published" else None, created, created,
            ),
        )


def seed(fresh: bool = False, *, verbose: bool = True) -> dict:
    """Create the demo workspace. Safe to call repeatedly."""
    if fresh:
        db.reset_db()
    else:
        db.init_db()

    existing = db.query_one("SELECT id FROM users WHERE lower(email) = ?", (config.DEMO_EMAIL.lower(),))
    if existing:
        if verbose:
            print(f"Demo workspace already exists (user #{existing['id']}) — nothing to do.")
        return {"user_id": existing["id"], "created": False}

    rng = random.Random(SEED)
    user_id = db.execute(
        """INSERT INTO users (email, name, password_hash, role, avatar_seed, created_at)
           VALUES (?, ?, ?, 'owner', ?, ?)""",
        (
            config.DEMO_EMAIL, "Alex Rivera", security.hash_password(config.DEMO_PASSWORD),
            "AR", db.utcnow(),
        ),
    )

    group_ids: list[int] = []
    for blueprint in GROUP_BLUEPRINTS:
        group = services.create_group(user_id, {**blueprint, "connected": True})
        services.touch_group_sync(group["id"])
        group_ids.append(group["id"])

    for group in db.query("SELECT * FROM groups WHERE owner_id = ? ORDER BY id", (user_id,)):
        _seed_posts(rng, user_id, group)

    _seed_guaranteed_spam(rng, user_id, group_ids)
    _seed_rules(user_id, group_ids)
    _seed_jobs(user_id)
    _seed_history(user_id, "Alex Rivera")

    counts = {
        "groups": db.scalar("SELECT COUNT(*) FROM groups WHERE owner_id = ?", (user_id,)),
        "posts": db.scalar("SELECT COUNT(*) FROM posts WHERE owner_id = ?", (user_id,)),
        "live_posts": db.scalar(
            "SELECT COUNT(*) FROM posts WHERE owner_id = ? AND deleted_at IS NULL", (user_id,)
        ),
        "trashed": db.scalar(
            "SELECT COUNT(*) FROM posts WHERE owner_id = ? AND deleted_at IS NOT NULL", (user_id,)
        ),
        "authors": db.scalar("SELECT COUNT(*) FROM authors WHERE owner_id = ?", (user_id,)),
        "rules": db.scalar("SELECT COUNT(*) FROM rules WHERE owner_id = ?", (user_id,)),
        "activity": db.scalar("SELECT COUNT(*) FROM activity WHERE owner_id = ?", (user_id,)),
    }
    if verbose:
        print(f"Seeded demo workspace for {config.DEMO_EMAIL} / {config.DEMO_PASSWORD}")
        for key, value in counts.items():
            print(f"  {key:<11} {value}")
    return {"user_id": user_id, "created": True, **counts}


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the Group Post Cleaner demo workspace")
    parser.add_argument("--fresh", action="store_true", help="drop and recreate the database first")
    args = parser.parse_args()
    seed(fresh=args.fresh)
    return 0


if __name__ == "__main__":
    sys.exit(main())
