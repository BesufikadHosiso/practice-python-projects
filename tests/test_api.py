"""End-to-end tests for the Group Post Cleaner API."""
from __future__ import annotations

import pytest


# --------------------------------------------------------------------- auth
class TestAuth:
    def test_register_login_and_me(self, client):
        response = client.post(
            "/api/auth/register",
            json={"email": "New@Example.com", "password": "correcthorse1", "name": "Dana Reyes"},
        )
        assert response.status_code == 201, response.text
        session = response.json()
        assert session["user"]["email"] == "new@example.com"
        assert session["user"]["avatar_seed"] == "DR"
        assert session["token"]

        login = client.post(
            "/api/auth/login", json={"email": "new@example.com", "password": "correcthorse1"}
        )
        assert login.status_code == 200

        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {session['token']}"})
        assert me.status_code == 200
        assert me.json()["name"] == "Dana Reyes"
        assert "password_hash" not in me.json()

    def test_login_rejects_wrong_password(self, client):
        client.post("/api/auth/register", json={
            "email": "a@b.com", "password": "correcthorse1", "name": "Ab Cd",
        })
        response = client.post("/api/auth/login", json={"email": "a@b.com", "password": "nope-nope"})
        assert response.status_code == 401

    def test_duplicate_email_is_rejected(self, client):
        payload = {"email": "dup@x.com", "password": "correcthorse1", "name": "Dup User"}
        assert client.post("/api/auth/register", json=payload).status_code == 201
        assert client.post("/api/auth/register", json=payload).status_code == 409

    def test_weak_password_is_rejected(self, client):
        response = client.post("/api/auth/register", json={
            "email": "weak@x.com", "password": "password", "name": "Weak Pass",
        })
        assert response.status_code == 422

    def test_every_api_route_requires_a_token(self, client):
        for path in ("/api/posts", "/api/groups", "/api/rules", "/api/stats/overview"):
            assert client.get(path).status_code == 401, path
        assert client.get("/api/posts", headers={"Authorization": "Bearer forged.token"}).status_code == 401

    def test_change_password_requires_the_current_one(self, auth_client):
        bad = auth_client.post("/api/auth/change-password", json={
            "current_password": "wrong", "new_password": "brandnewpass1",
        })
        assert bad.status_code == 400

        good = auth_client.post("/api/auth/change-password", json={
            "current_password": "supersecret1", "new_password": "brandnewpass1",
        })
        assert good.status_code == 204


# ------------------------------------------------------------- tenant isolation
class TestIsolation:
    def test_one_owner_cannot_see_another_owners_data(self, client):
        first = client.post("/api/auth/register", json={
            "email": "one@x.com", "password": "correcthorse1", "name": "One User",
        }).json()
        second = client.post("/api/auth/register", json={
            "email": "two@x.com", "password": "correcthorse1", "name": "Two User",
        }).json()

        group = client.post(
            "/api/groups",
            json={"name": "Private Group", "category": "Testing"},
            headers={"Authorization": f"Bearer {first['token']}"},
        ).json()

        other = {"Authorization": f"Bearer {second['token']}"}
        assert client.get("/api/groups", headers=other).json()["items"] == []
        assert client.get(f"/api/groups/{group['id']}", headers=other).status_code == 404

        post = client.post(
            "/api/posts",
            json={"group_id": group["id"], "author_name": "Someone", "message": "hello"},
            headers={"Authorization": f"Bearer {first['token']}"},
        ).json()
        assert client.get(f"/api/posts/{post['id']}", headers=other).status_code == 404
        assert client.delete(f"/api/posts/{post['id']}", headers=other).status_code == 404


# ------------------------------------------------------------------- groups
class TestGroups:
    def test_full_crud_cycle(self, auth_client):
        created = auth_client.post("/api/groups", json={
            "name": "Sourdough Bakers", "category": "Food & Drink",
            "privacy": "private", "members": 1200, "daily_posts": 9,
        })
        assert created.status_code == 201
        group = created.json()
        assert group["handle"] == "sourdough-bakers"
        assert group["connected"] is True
        assert group["stats"] == {"posts": 0, "published": 0, "pending": 0, "flagged": 0, "trashed": 0}

        updated = auth_client.patch(f"/api/groups/{group['id']}", json={
            "name": "Sourdough Bakers", "members": 2500, "privacy": "public",
        })
        assert updated.status_code == 200
        assert updated.json()["members"] == 2500
        assert updated.json()["privacy"] == "public"

        assert auth_client.get(f"/api/groups/{group['id']}").json()["name"] == "Sourdough Bakers"
        assert auth_client.get("/api/groups").json()["pagination"]["total"] == 1

        assert auth_client.delete(f"/api/groups/{group['id']}").status_code == 204
        assert auth_client.get(f"/api/groups/{group['id']}").status_code == 404

    def test_search_filters_by_name(self, auth_client):
        auth_client.post("/api/groups", json={"name": "Alpha Group"})
        auth_client.post("/api/groups", json={"name": "Beta Group"})
        items = auth_client.get("/api/groups", params={"q": "alpha"}).json()["items"]
        assert [group["name"] for group in items] == ["Alpha Group"]

    def test_sync_creates_posts(self, seeded_client):
        group = seeded_client.get("/api/groups").json()["items"][0]
        before = group["stats"]["posts"]
        result = seeded_client.post(f"/api/groups/{group['id']}/sync")
        assert result.status_code == 200
        assert result.json()["created"] >= 4
        after = seeded_client.get(f"/api/groups/{group['id']}").json()["stats"]["posts"]
        assert after == before + result.json()["created"]

    def test_health_endpoint(self, seeded_client):
        group = seeded_client.get("/api/groups").json()["items"][0]
        health = seeded_client.get(f"/api/groups/{group['id']}/health").json()
        assert 0 <= health["score"] <= 100
        assert health["group"]["id"] == group["id"]
        assert isinstance(health["by_type"], list)


# -------------------------------------------------------------------- posts
class TestPosts:
    @pytest.fixture()
    def group(self, auth_client):
        return auth_client.post("/api/groups", json={"name": "Test Group"}).json()

    def test_create_read_update_delete(self, auth_client, group):
        created = auth_client.post("/api/posts", json={
            "group_id": group["id"], "author_name": "Ada Lovelace",
            "message": "Check out https://bit.ly/free-stuff", "post_type": "link", "state": "pending",
        })
        assert created.status_code == 201
        post = created.json()
        assert post["state"] == "pending"
        assert post["group_name"] == "Test Group"
        assert post["avatar_seed"] == "AL"
        assert post["published_at"] is None

        fetched = auth_client.get(f"/api/posts/{post['id']}")
        assert fetched.json()["message"].startswith("Check out")

        updated = auth_client.patch(f"/api/posts/{post['id']}", json={
            "message": "Edited text", "state": "published",
        })
        assert updated.json()["message"] == "Edited text"
        assert updated.json()["state"] == "published"
        assert updated.json()["published_at"] is not None

        assert auth_client.delete(f"/api/posts/{post['id']}").status_code == 204
        # Soft delete: still readable, but hidden from the live list.
        assert auth_client.get(f"/api/posts/{post['id']}").json()["deleted_at"] is not None
        assert auth_client.get("/api/posts").json()["pagination"]["total"] == 0
        assert auth_client.get("/api/posts/trash").json()["pagination"]["total"] == 1

    def test_delete_then_restore_round_trip(self, auth_client, group):
        post = auth_client.post("/api/posts", json={
            "group_id": group["id"], "author_name": "Bob", "message": "keep me", "state": "flagged",
        }).json()

        auth_client.delete(f"/api/posts/{post['id']}")
        trashed = auth_client.get("/api/posts/trash").json()["items"][0]
        assert trashed["prior_state"] == "flagged"

        restored = auth_client.post(f"/api/posts/{post['id']}/restore")
        assert restored.json()["deleted_at"] is None
        assert restored.json()["state"] == "flagged", "restore must put it back the way it was"

    def test_purge_removes_the_row(self, auth_client, group):
        post = auth_client.post("/api/posts", json={
            "group_id": group["id"], "author_name": "Carl", "message": "gone",
        }).json()
        assert auth_client.post(f"/api/posts/{post['id']}/purge").status_code == 204
        assert auth_client.get(f"/api/posts/{post['id']}").status_code == 404

    def test_cannot_post_into_someone_elses_group(self, auth_client):
        response = auth_client.post("/api/posts", json={
            "group_id": 9999, "author_name": "Hacker", "message": "nope",
        })
        assert response.status_code == 400

    def test_filters_and_pagination(self, seeded_client):
        page = seeded_client.get("/api/posts", params={"per_page": 5, "page": 1}).json()
        assert page["pagination"]["per_page"] == 5
        assert len(page["items"]) == 5
        assert page["pagination"]["total"] > 5

        second = seeded_client.get("/api/posts", params={"per_page": 5, "page": 2}).json()
        assert {p["id"] for p in page["items"]}.isdisjoint({p["id"] for p in second["items"]})

        pending = seeded_client.get("/api/posts", params={"state": "pending"}).json()
        assert pending["pagination"]["total"] > 0
        assert all(post["state"] == "pending" for post in pending["items"])

        group_id = seeded_client.get("/api/groups").json()["items"][0]["id"]
        scoped = seeded_client.get("/api/posts", params={"group_id": group_id}).json()
        assert all(post["group_id"] == group_id for post in scoped["items"])

        linked = seeded_client.get("/api/posts", params={"contains_link": "true"}).json()
        assert all("http" in post["message"].lower() for post in linked["items"])

        reported = seeded_client.get("/api/posts", params={"min_reports": 3}).json()
        assert all(post["reports"] >= 3 for post in reported["items"])

    def test_sort_by_reports(self, seeded_client):
        items = seeded_client.get("/api/posts", params={"sort": "reports", "per_page": 10}).json()["items"]
        counts = [post["reports"] for post in items]
        assert counts == sorted(counts, reverse=True)

    def test_bulk_delete_and_undo(self, seeded_client):
        items = seeded_client.get("/api/posts", params={"per_page": 6}).json()["items"]
        ids = [post["id"] for post in items]
        before = seeded_client.get("/api/posts/trash").json()["pagination"]["total"]

        result = seeded_client.post("/api/posts/bulk", json={"ids": ids, "action": "delete"})
        assert result.json()["processed"] == len(ids)
        assert seeded_client.get("/api/posts/trash").json()["pagination"]["total"] == before + len(ids)

        undone = seeded_client.post("/api/posts/bulk", json={"ids": ids, "action": "restore"})
        assert undone.json()["processed"] == len(ids)
        assert seeded_client.get("/api/posts/trash").json()["pagination"]["total"] == before

    def test_bulk_approve_pending(self, seeded_client):
        pending = seeded_client.get("/api/posts", params={"state": "pending", "per_page": 4}).json()["items"]
        ids = [post["id"] for post in pending]
        seeded_client.post("/api/posts/bulk", json={"ids": ids, "action": "approve"})
        for post_id in ids:
            assert seeded_client.get(f"/api/posts/{post_id}").json()["state"] == "published"

    def test_bulk_rejects_unknown_ids(self, auth_client):
        response = auth_client.post("/api/posts/bulk", json={"ids": [123456], "action": "delete"})
        assert response.status_code == 404

    def test_empty_trash_purges_everything(self, seeded_client):
        assert seeded_client.get("/api/posts/trash").json()["pagination"]["total"] > 0
        result = seeded_client.delete("/api/posts/trash")
        assert result.json()["purged"] > 0
        assert seeded_client.get("/api/posts/trash").json()["pagination"]["total"] == 0


# ----------------------------------------------------------- bulk by filter
class TestBulkFilter:
    def test_dry_run_does_not_touch_anything(self, seeded_client):
        before = seeded_client.get("/api/stats/overview").json()["posts"]
        preview = seeded_client.post("/api/posts/bulk-filter", json={
            "filters": {"contains_link": True}, "action": "delete", "dry_run": True,
        })
        assert preview.json()["dry_run"] is True
        assert preview.json()["processed"] == 0
        assert preview.json()["matched"] > 0
        assert seeded_client.get("/api/stats/overview").json()["posts"] == before

    def test_sweep_by_keyword_moves_posts_to_trash(self, seeded_client):
        preview = seeded_client.post("/api/posts/bulk-filter", json={
            "filters": {"q": "crypto"}, "action": "delete", "dry_run": True,
        }).json()
        assert preview["matched"] > 0

        result = seeded_client.post("/api/posts/bulk-filter", json={
            "filters": {"q": "crypto"}, "action": "delete", "name": "Crypto sweep",
        }).json()
        assert result["processed"] == preview["matched"]
        assert result["job_id"] is not None

        remaining = seeded_client.get("/api/posts", params={"q": "crypto"}).json()["pagination"]["total"]
        assert remaining == 0

        jobs = seeded_client.get("/api/jobs").json()["items"]
        assert any(job["name"] == "Crypto sweep" for job in jobs)

    def test_sweep_can_be_scoped_to_one_group(self, seeded_client):
        groups = seeded_client.get("/api/groups").json()["items"]
        target, other = groups[0], groups[1]
        result = seeded_client.post("/api/posts/bulk-filter", json={
            "filters": {"group_ids": [target["id"]]}, "action": "flag", "name": "Flag one group",
        }).json()
        assert result["processed"] > 0
        # The other group must be untouched.
        others = seeded_client.get("/api/posts", params={"group_id": other["id"], "state": "flagged"}).json()
        assert all(post["group_id"] == other["id"] for post in others["items"])


# -------------------------------------------------------------------- rules
class TestRules:
    def test_crud_and_toggle(self, auth_client):
        created = auth_client.post("/api/rules", json={
            "name": "No crypto", "condition_type": "keyword",
            "condition_value": "crypto,forex", "action": "delete", "severity": "high",
        })
        assert created.status_code == 201
        rule = created.json()
        assert rule["enabled"] is True

        updated = auth_client.patch(f"/api/rules/{rule['id']}", json={
            "name": "No crypto", "action": "flag", "threshold": 2,
        })
        assert updated.json()["action"] == "flag"

        toggled = auth_client.post(f"/api/rules/{rule['id']}/toggle")
        assert toggled.json()["enabled"] is False

        assert auth_client.delete(f"/api/rules/{rule['id']}").status_code == 204
        assert auth_client.get(f"/api/rules/{rule['id']}").status_code == 404

    def test_keyword_rule_requires_a_value(self, auth_client):
        response = auth_client.post("/api/rules", json={
            "name": "Broken rule", "condition_type": "keyword", "condition_value": "  ",
        })
        assert response.status_code == 422

    def test_keyword_rule_only_matches_its_keywords(self, seeded_client):
        rule = seeded_client.post("/api/rules", json={
            "name": "Only crypto", "condition_type": "keyword", "condition_value": "crypto",
            "action": "delete",
        }).json()
        preview = seeded_client.get(f"/api/rules/{rule['id']}/preview").json()
        assert preview["matched"] > 0, "the seeded corpus must contain crypto spam"
        assert all("crypto" in post["message"].lower() for post in preview["items"])

        run = seeded_client.post(f"/api/rules/{rule['id']}/run", json={"dry_run": False}).json()
        assert run["processed"] == preview["matched"]
        # Re-previewing is the honest check: the rule must now find nothing.
        # (The free-text `q` filter also matches author names, so it would still
        # return the posts written by the member called "Crypto King 24".)
        assert seeded_client.get(f"/api/rules/{rule['id']}/preview").json()["matched"] == 0

        after = seeded_client.get(f"/api/rules/{rule['id']}").json()
        assert after["runs"] == 1
        assert after["affected"] == run["processed"]
        assert after["last_run_at"] is not None

    def test_dry_run_endpoint_for_unsaved_rule(self, seeded_client):
        result = seeded_client.post("/api/rules/dry-run", json={
            "name": "Preview only", "condition_type": "reported", "threshold": 1, "action": "delete",
        }).json()
        assert result["dry_run"] is True
        assert result["matched"] > 0
        assert result["processed"] == 0

    def test_run_all_rules(self, seeded_client):
        result = seeded_client.post("/api/rules/run-all").json()
        assert result["rules"] >= 1

    def test_duplicate_rule_catches_repeats(self, seeded_client):
        rule = seeded_client.post("/api/rules", json={
            "name": "Dupes", "condition_type": "duplicate", "action": "delete",
        }).json()
        preview = seeded_client.get(f"/api/rules/{rule['id']}/preview").json()
        assert preview["matched"] > 0, "the seed data contains repeated spam messages"

    def test_banned_author_rule(self, seeded_client):
        rule = seeded_client.post("/api/rules", json={
            "name": "Banned sweep", "condition_type": "banned_author", "action": "delete",
        }).json()
        preview = seeded_client.get(f"/api/rules/{rule['id']}/preview").json()
        assert isinstance(preview["items"], list)


# ------------------------------------------------------------------ authors
class TestAuthors:
    def test_ban_sweeps_their_posts(self, seeded_client):
        authors = seeded_client.get("/api/authors").json()["items"]
        spammer = next(author for author in authors if author["posts"] > 1 and not author["is_banned"])

        result = seeded_client.post(f"/api/authors/{spammer['id']}/ban").json()
        assert result["is_banned"] is True
        assert result["swept"] > 0
        assert seeded_client.get("/api/posts", params={"author_id": spammer["id"]}).json()["pagination"]["total"] == 0

        unbanned = seeded_client.post(f"/api/authors/{spammer['id']}/ban").json()
        assert unbanned["is_banned"] is False

    def test_author_crud(self, auth_client):
        created = auth_client.post("/api/authors", json={"name": "Nuisance Nick", "risk_score": 80})
        assert created.status_code == 201
        author = created.json()
        assert author["handle"] == "@nuisance-nick"

        updated = auth_client.patch(f"/api/authors/{author['id']}", json={
            "name": "Nuisance Nick", "is_banned": True,
        })
        assert updated.json()["is_banned"] is True

        assert auth_client.delete(f"/api/authors/{author['id']}").status_code == 204
        assert auth_client.get(f"/api/authors/{author['id']}").status_code == 404

    def test_purge_author_posts(self, seeded_client):
        authors = seeded_client.get("/api/authors").json()["items"]
        target = next(author for author in authors if author["posts"] > 0)
        result = seeded_client.post(f"/api/authors/{target['id']}/purge-posts").json()
        assert result["purged"] > 0


# ------------------------------------------------------- jobs / activity / stats
class TestObservability:
    def test_jobs_record_sweeps_and_can_be_cleared(self, seeded_client):
        assert len(seeded_client.get("/api/jobs").json()["items"]) > 0
        seeded_client.post("/api/posts/bulk-filter", json={
            "filters": {"states": ["pending"], "older_than_days": 30}, "action": "delete", "name": "Stale pending",
        })
        names = [job["name"] for job in seeded_client.get("/api/jobs").json()["items"]]
        assert "Stale pending" in names
        assert seeded_client.delete("/api/jobs").json()["removed"] > 0
        assert seeded_client.get("/api/jobs").json()["items"] == []

    def test_activity_records_moderation(self, seeded_client):
        items = seeded_client.get("/api/posts", params={"per_page": 1}).json()["items"]
        seeded_client.post("/api/posts/bulk", json={"ids": [items[0]["id"]], "action": "delete"})
        actions = [entry["action"] for entry in seeded_client.get("/api/activity").json()["items"]]
        assert "post.deleted" in actions

    def test_activity_filters_and_clear(self, seeded_client):
        only_posts = seeded_client.get("/api/activity", params={"action": "post."}).json()
        assert all(entry["action"].startswith("post.") for entry in only_posts["items"])
        assert seeded_client.delete("/api/activity").json()["removed"] > 0
        assert seeded_client.get("/api/activity").json()["items"] == []

    def test_stats_overview_shape(self, seeded_client):
        stats = seeded_client.get("/api/stats/overview").json()
        assert stats["posts"]["live"] > 0
        assert stats["posts"]["live"] == stats["posts"]["published"] + stats["posts"]["pending"] \
            + stats["posts"]["flagged"] + stats["posts"]["scheduled"]
        assert stats["groups"]["total"] == 6
        assert 0 <= stats["cleanup"]["health"] <= 100
        assert len(stats["top_groups"]) == 5
        assert stats["spam_patterns"]

    def test_stats_react_to_a_sweep(self, seeded_client):
        before = seeded_client.get("/api/stats/overview").json()["posts"]["live"]
        seeded_client.post("/api/posts/bulk-filter", json={
            "filters": {"contains_link": True}, "action": "delete", "name": "Link sweep",
        })
        after = seeded_client.get("/api/stats/overview").json()["posts"]
        assert after["live"] < before
        assert after["trashed"] > 0

    def test_timeline_is_bucketed_by_day(self, seeded_client):
        timeline = seeded_client.get("/api/stats/timeline", params={"days": 7}).json()
        assert len(timeline["items"]) == 7
        assert {"date", "deleted", "pending", "flagged"} <= set(timeline["items"][0])


# ------------------------------------------------------------- app plumbing
class TestPlumbing:
    def test_empty_database_seeds_itself_on_startup(self, client):
        """A fresh checkout (or a wiped data/) must serve a working app."""
        response = client.post(
            "/api/auth/login", json={"email": "admin@demo.com", "password": "demo1234"}
        )
        assert response.status_code == 200, "the demo workspace should exist without a manual seed"
        client.headers["Authorization"] = f"Bearer {response.json()['token']}"
        stats = client.get("/api/stats/overview").json()
        assert stats["groups"]["total"] == 6
        assert stats["posts"]["live"] > 100
        assert stats["cleanup"]["rules_total"] == 9

    def test_health_endpoint_is_public(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_openapi_schema_is_served(self, client):
        assert client.get("/api/openapi.json").status_code == 200

    def test_unknown_api_path_returns_json_404(self, client):
        response = client.get("/api/does-not-exist")
        assert response.status_code == 404
        assert response.json() == {"detail": "Not found"}

    def test_seed_is_idempotent(self, seeded_client):
        from app.seed import seed

        again = seed(fresh=False, verbose=False)
        assert again["created"] is False


# --------------------------------------------------------------- security unit
class TestSecurity:
    def test_password_hashing_round_trip(self):
        from app import security

        stored = security.hash_password("hunter2hunter2")
        assert stored.startswith("pbkdf2$")
        assert security.verify_password("hunter2hunter2", stored) is True
        assert security.verify_password("wrong", stored) is False
        assert security.verify_password("hunter2hunter2", "not-a-hash") is False

    def test_tokens_are_signed_and_expire(self):
        from app import security

        token, expires_at = security.create_token(7, "owner", ttl=60)
        payload = security.decode_token(token)
        assert payload["sub"] == 7
        assert expires_at > payload["iat"]

        body, _, signature = token.partition(".")
        forged = f"{body}.{'A' * len(signature)}"
        assert security.decode_token(forged) is None
        assert security.decode_token("garbage") is None

        expired, _ = security.create_token(7, "owner", ttl=-10)
        assert security.decode_token(expired) is None

    def test_initials(self):
        from app import security

        assert security.initials("Ada Lovelace") == "AL"
        assert security.initials("Prince") == "PR"
        assert security.initials("") == "??"
