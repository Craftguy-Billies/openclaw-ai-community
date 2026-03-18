import unittest
import os
import tempfile
import importlib


os.environ["APP_DISABLE_AUTO_LOOP"] = "1"
os.environ["FORCE_FAKE_COMPLETIONS"] = "1"
os.environ["OPENCLAW_USE"] = "0"

tmp_db = tempfile.NamedTemporaryFile(delete=False)
tmp_db.close()
os.environ["COMMUNITY_DB_PATH"] = tmp_db.name

import app as app_module
importlib.reload(app_module)


class AppRoutesTest(unittest.TestCase):
    def setUp(self):
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        app_module.reset_world()

    def test_index_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Community Feed", response.data)

    def test_auto_step_adds_activity(self):
        before = len(app_module.fetch_feed())
        response = self.client.post("/auto-step", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        after = len(app_module.fetch_feed())
        self.assertGreaterEqual(after, before)

    def test_chat_route_works(self):
        before_posts = len(app_module.fetch_feed())
        response = self.client.post("/chat", data={"message": "hi ayaka"}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        after_posts = len(app_module.fetch_feed())
        self.assertEqual(after_posts, before_posts)
        html = response.data.decode("utf-8")
        self.assertIn("Kamisato Ayaka", html)

    def test_clear_db_keep_two_leaves_exactly_two_seed_posts(self):
        feed_before = app_module.fetch_feed()
        self.assertGreaterEqual(len(feed_before), 2)

        first_post_id = feed_before[0]["id"]
        app_module.create_comment(first_post_id, "You", "temp comment", "human")
        app_module.insert_chat_message("You", "temp msg")
        app_module.add_memory_event(1, "user-message", "temp memory", "test")

        response = self.client.post("/clear-db-keep-two", follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        feed_after = app_module.fetch_feed()
        self.assertEqual(len(feed_after), 2)

        with app_module.DB_LOCK:
            conn = app_module.db_connection()
            comments = conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
            chats = conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0]
            memories = conn.execute("SELECT COUNT(*) FROM memory_events").fetchone()[0]
            conn.close()

        self.assertEqual(comments, 0)
        self.assertEqual(chats, 0)
        self.assertEqual(memories, 0)

    def test_control_button_routes_work(self):
        routes = [
            "/auto-step",
            "/sync-now",
            "/toggle-auto",
            "/toggle-force-post",
            "/reset",
            "/clear-db-keep-two",
        ]
        for route in routes:
            response = self.client.post(route, follow_redirects=True)
            self.assertEqual(response.status_code, 200, msg=f"Route failed: {route}")

    def test_dm_private_text_does_not_leak_to_community(self):
        private_token = "PRIVATE_TOKEN_8472_DO_NOT_LEAK"

        with app_module.DB_LOCK:
            conn = app_module.db_connection()
            comments_before = conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
            posts_before = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
            conn.close()

        response = self.client.post(
            "/chat",
            data={"message": f"this is secret {private_token}", "agent_name": "Kamisato Ayaka"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)

        with app_module.DB_LOCK:
            conn = app_module.db_connection()
            comments_after_chat = conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
            posts_after_chat = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
            conn.close()

        self.assertEqual(comments_after_chat, comments_before)
        self.assertEqual(posts_after_chat, posts_before)

        for _ in range(6):
            app_module.auto_activity_step()

        feed = app_module.fetch_feed(limit=100)
        combined = []
        for post in feed:
            combined.append(str(post["caption"]))
            for comment in post["comments"]:
                combined.append(str(comment["content"]))
        text_blob = "\n".join(combined)

        self.assertNotIn(private_token, text_blob)

    def test_relationship_instruction_rules(self):
        sibling_rule = app_module.community_relationship_instruction("Kamisato Ayaka", "Kamisato Ayato")
        self.assertIn("sibling", sibling_rule.lower())
        self.assertIn("non-romantic", sibling_rule.lower())
        self.assertIn("pet names", sibling_rule.lower())

        user_rule = app_module.community_relationship_instruction("Kamisato Ayaka", "You")
        self.assertIn("user", user_rule.lower())
        self.assertIn("intimate", user_rule.lower())
        self.assertNotIn("pet names", user_rule.lower())

    def test_build_comment_includes_relationship_context(self):
        agent = app_module.get_agent_by_name("Kamisato Ayaka")
        self.assertIsNotNone(agent)

        captured = {}
        original_generate = app_module.backend.generate

        def fake_generate(agent_payload, prompt, **kwargs):
            captured["prompt"] = prompt
            return "friendly update"

        app_module.backend.generate = fake_generate
        try:
            app_module.build_comment(agent, "small life update before sleep ✨", target_post_author_label="Kamisato Ayato")
        finally:
            app_module.backend.generate = original_generate

        prompt = captured.get("prompt", "")
        self.assertIn("Post owner: Kamisato Ayato", prompt)
        self.assertIn("sibling", prompt.lower())
        self.assertIn("non-romantic", prompt.lower())
        self.assertIn("never flirt", prompt.lower())
        self.assertIn("romantic pet names", prompt.lower())

    def test_invalid_cron_caption_detection(self):
        ayaka = app_module.get_agent_by_name("Kamisato Ayaka")
        self.assertIsNotNone(ayaka)

        self.assertTrue(app_module.is_invalid_cron_caption("(Ayato-style composed first-person update)", ayaka))
        self.assertTrue(app_module.is_invalid_cron_caption("(Ayaka-style graceful first-person update)", ayaka))
        self.assertFalse(app_module.is_invalid_cron_caption("i took a quiet evening walk and felt peaceful.", ayaka))

    def test_platonic_rewrite_runs_for_non_user_target(self):
        agent = app_module.get_agent_by_name("Kamisato Ayaka")
        self.assertIsNotNone(agent)

        calls = {"count": 0, "prompt": "", "temperature": None}
        original_generate = app_module.backend.generate

        def fake_generate(agent_payload, prompt, **kwargs):
            calls["count"] += 1
            calls["prompt"] = prompt
            calls["temperature"] = kwargs.get("temperature")
            return "hope your evening stays peaceful."

        app_module.backend.generate = fake_generate
        try:
            output = app_module.openclaw_platonic_rewrite(
                agent,
                "i'm happy for you, my love",
                target_label="Kamisato Ayato",
                max_words=18,
                session_scope="test-scope",
            )
        finally:
            app_module.backend.generate = original_generate

        self.assertEqual(calls["count"], 1)
        self.assertIn("NOT the user", calls["prompt"])
        self.assertIn("No flirting", calls["prompt"])
        self.assertEqual(calls["temperature"], 0.0)
        self.assertEqual(output, "hope your evening stays peaceful.")

    def test_platonic_rewrite_skips_for_user_target(self):
        agent = app_module.get_agent_by_name("Kamisato Ayaka")
        self.assertIsNotNone(agent)

        original_generate = app_module.backend.generate

        def fail_generate(*args, **kwargs):
            raise AssertionError("backend.generate should not be called for user target")

        app_module.backend.generate = fail_generate
        try:
            output = app_module.openclaw_platonic_rewrite(
                agent,
                "my love, i'm here",
                target_label="You",
                max_words=18,
                session_scope="test-scope",
            )
        finally:
            app_module.backend.generate = original_generate

        self.assertEqual(output, "my love, i'm here")

    def test_strict_openclaw_profile_selection_by_scope(self):
        backend = app_module.AgentBackend()
        backend.strict_openclaw_only = True
        backend.chat_profile_name = "chat-prof"
        backend.community_profile_name = "community-prof"

        captured = {"profile": None, "session_id": None}
        original_cli = backend._openclaw_cli

        def fake_cli(prompt, session_id, agent, timeout=45, profile_name=None):
            captured["profile"] = profile_name
            captured["session_id"] = session_id
            return "ok"

        backend._openclaw_cli = fake_cli
        try:
            backend._generate_openclaw(
                {"name": "A", "username": "@a", "persona": "p", "style": "s", "profile": "luna", "soul_file": "SOUL-luna.md"},
                "hello",
                max_tokens=10,
                temperature=0.1,
                session_scope="chat",
            )
            self.assertEqual(captured["profile"], "chat-prof")

            backend._generate_openclaw(
                {"name": "A", "username": "@a", "persona": "p", "style": "s", "profile": "luna", "soul_file": "SOUL-luna.md"},
                "hello",
                max_tokens=10,
                temperature=0.1,
                session_scope="community-comment-platonic",
            )
            self.assertEqual(captured["profile"], "community-prof")
        finally:
            backend._openclaw_cli = original_cli

    def test_threaded_comment_order_is_parent_then_children(self):
        feed = app_module.fetch_feed()
        self.assertGreaterEqual(len(feed), 1)
        post_id = int(feed[0]["id"])

        parent_id = app_module.create_comment(post_id, "You", "root comment", "human")
        child_id = app_module.create_comment(post_id, "You", "child comment", "human-reply", parent_comment_id=parent_id)
        grandchild_id = app_module.create_comment(post_id, "You", "grandchild comment", "human-reply", parent_comment_id=child_id)
        sibling_root_id = app_module.create_comment(post_id, "You", "second root", "human")

        post = next(item for item in app_module.fetch_feed(limit=50) if int(item["id"]) == post_id)
        ids = [int(comment["id"]) for comment in post["comments"]]

        parent_pos = ids.index(parent_id)
        child_pos = ids.index(child_id)
        grandchild_pos = ids.index(grandchild_id)
        sibling_root_pos = ids.index(sibling_root_id)

        self.assertLess(parent_pos, child_pos)
        self.assertLess(child_pos, grandchild_pos)
        self.assertLess(parent_pos, sibling_root_pos)

    def test_user_reply_can_continue_with_ai_reply(self):
        feed = app_module.fetch_feed()
        self.assertGreaterEqual(len(feed), 1)
        post_id = int(feed[0]["id"])

        base_comment_id = app_module.create_comment(post_id, "You", "start thread", "human")
        user_reply_id = app_module.create_comment(
            post_id,
            "You",
            "continue reply",
            "human-reply",
            parent_comment_id=base_comment_id,
        )
        app_module.enqueue_comment_reply_job(user_reply_id, post_id)

        original_chance = app_module.SLOW_PROFILE_COMMENT_REPLY_CHANCE
        app_module.SLOW_PROFILE_COMMENT_REPLY_CHANCE = 1.0
        try:
            processed = app_module.process_pending_comment_replies(limit=10)
        finally:
            app_module.SLOW_PROFILE_COMMENT_REPLY_CHANCE = original_chance

        self.assertGreaterEqual(processed, 1)

        with app_module.DB_LOCK:
            conn = app_module.db_connection()
            ai_follow_up = conn.execute(
                "SELECT id, parent_comment_id, author_label, source FROM comments WHERE parent_comment_id = ? ORDER BY id DESC LIMIT 1",
                (user_reply_id,),
            ).fetchone()
            conn.close()

        self.assertIsNotNone(ai_follow_up)
        self.assertNotEqual(str(ai_follow_up["author_label"]).strip().lower(), "you")
        self.assertIn("openclaw-comment-reply", str(ai_follow_up["source"]))


if __name__ == "__main__":
    unittest.main()
