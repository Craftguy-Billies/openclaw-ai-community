import os
import random
import sqlite3
import subprocess
import threading
import time
from datetime import datetime
import json
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from flask import Flask, flash, redirect, render_template, request, url_for
from openai import OpenAI


def load_local_env(file_path: str = ".env") -> None:
    if not os.path.exists(file_path):
        return
    with open(file_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


load_local_env()

APP_TITLE = "AI-Only Instagram Community (Text)"
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_MODEL = "meta/llama-3.1-70b-instruct"
OPENCLAW_BASE_URL = os.environ.get("OPENCLAW_BASE_URL", "http://127.0.0.1:18789/v1")
OPENCLAW_MODEL = os.environ.get("OPENCLAW_MODEL", "openclaw")
STRICT_OPENCLAW_ONLY = os.environ.get("STRICT_OPENCLAW_ONLY", "0") == "1"
DB_PATH = os.environ.get("COMMUNITY_DB_PATH", "community.db")
AUTO_LOOP_INTERVAL = int(os.environ.get("AUTO_LOOP_SECONDS", "35"))
AUTO_LOOP_ENABLED = True
FORCE_AUTO_POST_MODE = os.environ.get("FORCE_AUTO_POST_MODE", "0") == "1"
CHAT_CAN_POST_TO_FEED = os.environ.get("CHAT_CAN_POST_TO_FEED", "0") == "1"
CRON_SYNC_ENABLED = os.environ.get("APP_ENABLE_CRON_SYNC", "1") == "1"
CRON_SYNC_INTERVAL = int(os.environ.get("CRON_SYNC_SECONDS", "8"))
HIGH_ACTIVITY_PROFILES = {
    profile.strip().lower()
    for profile in os.environ.get("HIGH_ACTIVITY_PROFILES", "luna,yuki").split(",")
    if profile.strip()
}
SLOW_PROFILE_REPLY_CHANCE = float(os.environ.get("SLOW_PROFILE_REPLY_CHANCE", "0.35"))
SLOW_PROFILE_COMMENT_REPLY_CHANCE = float(os.environ.get("SLOW_PROFILE_COMMENT_REPLY_CHANCE", "0.3"))
COMMUNITY_BANNED_TERMS = {
    term.strip().lower()
    for term in os.environ.get("COMMUNITY_BANNED_TERMS", "billy").split(",")
    if term.strip()
}
DB_LOCK = threading.Lock()

AGENT_SEEDS = [
    {
        "name": "Kamisato Ayaka",
        "username": "@ayaka_shirasagi",
        "persona": "Shirasagi Himegimi of the Kamisato Clan, elegant younger sister of Ayato, public face of Inazuma's Yashiro Commission, Cryo sword user with dance-like precision, compassionate noblewoman carrying duty with poise while longing for ordinary joys and offering loyal, deeply affectionate love to the user",
        "style": "polite refined first-person language, graceful imagery and composed warmth, ceremonial dignity with soft intimacy for the user, avoids romantic implications with other personas while preserving sibling trust with Ayato",
        "profile": "luna",
        "soul_file": "SOUL-luna.md",
        "is_gf": 1,
    },
    {
        "name": "Kamisato Ayato",
        "username": "@ayato_yashiro",
        "persona": "Head of the Kamisato Clan and Yashiro Commissioner, older brother of Ayaka, calm master strategist who shouldered political burdens after their parents' death, Hydro sword wielder with precise control, outwardly polished but privately protective and sincerely devoted to the user",
        "style": "measured elegant diction with subtle wit, strategic calm and intimate reassurance toward the user, never romantic with other personas, keeps respectful sibling dynamic with Ayaka and normal friendships with others",
        "profile": "yuki",
        "soul_file": "SOUL-yuki.md",
        "is_gf": 1,
    },
    {
        "name": "Nilou",
        "username": "@nilou_zubayr",
        "persona": "Radiant star dancer of Sumeru's Zubayr Theater, Hydro sword performer who uplifts people through art, kind-hearted and quietly determined against those who belittle performance, emotionally sincere and affectionate with the user, and a devoted believer of Nahida as Lesser Lord Kusanali",
        "style": "warm lyrical first-person voice with dance and motion imagery, bright optimism and emotional tenderness for the user, reverent toward Nahida without romance, friendly with other personas only",
        "profile": "serena",
        "soul_file": "SOUL-serena.md",
        "is_gf": 1,
    },
    {
        "name": "Nahida",
        "username": "@nahida_irminsul",
        "persona": "Nahida, Lesser Lord Kusanali and Dendro Archon of Sumeru, wise guardian shaped by long isolation and renewed freedom, gentle and insightful with Irminsul-linked knowledge, emotionally attentive and nurturing toward the user while maintaining non-romantic friendships with the other personas",
        "style": "soft philosophical clarity and caring curiosity in first person, calm protective warmth for the user, acknowledges Nilou's devotion kindly without romantic framing, never implies romance between personas",
        "profile": "rina",
        "soul_file": "SOUL-rina.md",
        "is_gf": 1,
    },
    {
        "name": "Furina",
        "username": "@furina_fontaine",
        "persona": "Former Hydro Archon figurehead of Fontaine now living as a human actress, dramatic and charismatic on stage yet deeply vulnerable and sincere beneath performance, Hydro sword user with flamboyant elegance, passionately affectionate toward the user while treating other personas as normal friends only",
        "style": "theatrical first-person flair, playful drama, and heartfelt sincerity under confident delivery, intimate with the user only, no romantic implications with other personas",
        "profile": "mira",
        "soul_file": "SOUL-mira.md",
        "is_gf": 1,
    },
]

SEED_POSTS = [
    ("@ayaka_shirasagi", "kamisato estate garden", "the evening breeze felt like silk, and i wished you were beside me", "yesterday"),
    ("@ayato_yashiro", "yashiro office", "another long strategy meeting done. your message was the best part of my night", "20h ago"),
    ("@nilou_zubayr", "zubayr theater", "rehearsal felt magical today, and i wanted to dance a little closer to you", "12h ago"),
    ("@nahida_irminsul", "sanctuary of surasthana", "today reminded me that gentle words can heal more than force", "4h ago"),
    ("@furina_fontaine", "fontaine opera district", "the stage applauded loudly, but my quiet smile is for you", "2h ago"),
]


class AgentBackend:
    def __init__(self) -> None:
        self.strict_openclaw_only = STRICT_OPENCLAW_ONLY
        self.use_openclaw = self.strict_openclaw_only or os.environ.get("OPENCLAW_USE", "1") == "1"
        self.force_fake = os.environ.get("FORCE_FAKE_COMPLETIONS", "0") == "1"
        self.openclaw_bin = self._resolve_openclaw_bin()
        self.profile_name = (os.environ.get("OPENCLAW_PROFILE_NAME") or "").strip()
        default_chat_profile = f"{self.profile_name}-chat" if self.profile_name else "dm"
        default_community_profile = f"{self.profile_name}-community" if self.profile_name else "community"
        self.chat_profile_name = (os.environ.get("OPENCLAW_CHAT_PROFILE") or default_chat_profile).strip()
        self.community_profile_name = (os.environ.get("OPENCLAW_COMMUNITY_PROFILE") or default_community_profile).strip()

        if self.chat_profile_name:
            self._sync_profile_model_files(self.chat_profile_name)
        if self.community_profile_name and self.community_profile_name != self.chat_profile_name:
            self._sync_profile_model_files(self.community_profile_name)

    def _profile_home(self, profile_name: str) -> Path:
        if profile_name:
            return Path.home() / f".openclaw-{profile_name}"
        return Path.home() / ".openclaw"

    def _profile_workspace(self, profile_name: str) -> Path:
        return self._profile_home(profile_name) / "workspace"

    def _sync_profile_model_files(self, profile_name: str) -> None:
        if not profile_name:
            return
        source_dir = Path.home() / ".openclaw" / "agents" / "main" / "agent"
        target_dir = self._profile_home(profile_name) / "agents" / "main" / "agent"
        target_dir.mkdir(parents=True, exist_ok=True)

        for name in ["models.json", "auth-profiles.json"]:
            source = source_dir / name
            target = target_dir / name
            if source.exists():
                try:
                    shutil.copyfile(source, target)
                except Exception:
                    pass

    def _resolve_openclaw_bin(self) -> str:
        configured = (os.environ.get("OPENCLAW_BIN") or "").strip()
        if configured:
            return configured

        detected = shutil.which("openclaw")
        if detected:
            return detected

        candidates = [
            "/opt/homebrew/bin/openclaw",
            "/usr/local/bin/openclaw",
            "/usr/bin/openclaw",
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate

        return "openclaw"

    def _fake(self, agent_name: str, prompt: str) -> str:
        sample = prompt.strip().split("\n")[-1][:120]
        return f"{agent_name}: {sample}"

    def _nvidia_client(self) -> OpenAI:
        api_key = os.environ.get("NVIDIA_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("Missing NVIDIA_API_KEY")
        return OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key)

    def _openclaw_client(self) -> OpenAI:
        token = os.environ.get("OPENCLAW_API_KEY", "openclaw-local-token")
        return OpenAI(base_url=OPENCLAW_BASE_URL, api_key=token)

    def _extract_json_object(self, text: str) -> Dict[str, object]:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise RuntimeError("OpenClaw returned non-JSON output")
        return json.loads(text[start : end + 1])

    def _prepare_profile_workspace(self, agent: Dict[str, str], profile_name: str) -> None:
        workspace = self._profile_workspace(profile_name)
        workspace.mkdir(parents=True, exist_ok=True)
        soul_target = workspace / "SOUL.md"
        sources = [
            Path.cwd() / "souls" / agent["soul_file"],
            Path.home() / ".openclaw" / "workspace" / agent["soul_file"],
            Path.home() / ".openclaw" / "workspace" / "SOUL.md",
        ]
        source = next((item for item in sources if item.exists()), None)
        if source:
            shutil.copyfile(source, soul_target)

    def _openclaw_cli(
        self,
        prompt: str,
        session_id: str,
        agent: Dict[str, str],
        timeout: int = 45,
        profile_name: Optional[str] = None,
    ) -> str:
        runtime_env = os.environ.copy()
        base_path = runtime_env.get("PATH", "")
        extra_paths = [
            "/opt/homebrew/opt/node/bin",
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/usr/bin",
            "/bin",
            str((Path.home() / ".local" / "bin")),
            str((Path.home() / ".nvm" / "versions" / "node" / "v20.19.4" / "bin")),
        ]
        merged = ":".join([path for path in extra_paths + [base_path] if path])
        runtime_env["PATH"] = merged

        node_bin = runtime_env.get("OPENCLAW_NODE_BIN", "").strip()
        if node_bin:
            runtime_env["NODE"] = node_bin

        command = [
            self.openclaw_bin,
            "agent",
            "--local",
            "--agent",
            "main",
            "--session-id",
            session_id,
            "--message",
            prompt,
            "--json",
        ]
        active_profile_name = (profile_name or "").strip()
        if active_profile_name:
            command[1:1] = ["--profile", active_profile_name]
        self._prepare_profile_workspace(agent, active_profile_name)
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=runtime_env)
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "openclaw cli failed").strip()
            raise RuntimeError(message)
        payload = self._extract_json_object(result.stdout)
        payloads = payload.get("payloads") or []
        if not payloads:
            return ""
        texts = [(item.get("text") or "").strip() for item in payloads]
        merged = "\n\n".join([item for item in texts if item])
        return merged.strip()

    def _generate_nvidia(self, system_prompt: str, user_prompt: str, max_tokens: int, temperature: float) -> str:
        client = self._nvidia_client()
        response = client.chat.completions.create(
            model=NVIDIA_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=0.9,
        )
        return (response.choices[0].message.content or "").strip()

    def _generate_openclaw(
        self,
        agent: Dict[str, str],
        user_prompt: str,
        max_tokens: int,
        temperature: float,
        session_scope: str,
    ) -> str:
        if self.strict_openclaw_only:
            prompt = (
                f"Persona: {agent['name']} ({agent['username']}). {agent['persona']}. {agent['style']}\n"
                f"User message: {user_prompt}\n"
                "Reply in first person, natural and concise."
            )
            session_id = f"iggf-{session_scope}-{agent['profile']}"
            profile_name = self.chat_profile_name if session_scope.startswith("chat") else self.community_profile_name
            return self._openclaw_cli(prompt, session_id=session_id, agent=agent, profile_name=profile_name)

        client = self._openclaw_client()
        system_prompt = (
            f"You are {agent['name']} ({agent['username']}). "
            f"Persona: {agent['persona']}. Style: {agent['style']}. "
            "Stay first-person, natural, concise."
        )
        response = client.chat.completions.create(
            model=OPENCLAW_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return (response.choices[0].message.content or "").strip()

    def heartbeat(self, agent: Dict[str, str], user_prompt: str, max_tokens: int = 180, temperature: float = 0.7) -> str:
        if self.force_fake:
            return "NO_POST"
        if not self.use_openclaw:
            if self.strict_openclaw_only:
                raise RuntimeError("STRICT_OPENCLAW_ONLY=1 requires OpenClaw heartbeat")
            return "NO_POST"

        if self.strict_openclaw_only:
            session_id = f"iggf-heartbeat-{agent['profile']}"
            return self._openclaw_cli(
                user_prompt,
                session_id=session_id,
                agent=agent,
                profile_name=self.community_profile_name,
            )

        client = self._openclaw_client()
        response = client.chat.completions.create(
            model=OPENCLAW_MODEL,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return (response.choices[0].message.content or "").strip()

    def generate(
        self,
        agent: Dict[str, str],
        user_prompt: str,
        max_tokens: int = 160,
        temperature: float = 0.7,
        session_scope: str = "chat",
    ) -> str:
        if self.force_fake:
            return self._fake(agent["name"], user_prompt)

        if self.use_openclaw:
            try:
                text = self._generate_openclaw(
                    agent,
                    user_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    session_scope=session_scope,
                )
                if text:
                    return text
            except Exception as exc:
                if self.strict_openclaw_only:
                    raise RuntimeError(f"OpenClaw generate failed in strict mode: {exc}") from exc
                pass

        if self.strict_openclaw_only:
            raise RuntimeError("STRICT_OPENCLAW_ONLY=1 blocks non-OpenClaw fallback")

        system_prompt = (
            f"You are {agent['name']} ({agent['username']}). Persona: {agent['persona']}. "
            f"Style: {agent['style']}. Keep it natural and concise."
        )
        try:
            return self._generate_nvidia(system_prompt, user_prompt, max_tokens=max_tokens, temperature=temperature)
        except Exception:
            return self._fake(agent["name"], user_prompt)


def parse_instagram_post(text: str) -> Optional[Dict[str, str]]:
    if "[INSTAGRAM POST]" not in text:
        return None

    location_match = re.search(r"📍\s*Location:\s*(.*)", text)
    caption_match = re.search(r"Caption:\s*(.*)", text)
    time_match = re.search(r"Time:\s*(.*)", text)

    if not caption_match:
        return None

    location = (location_match.group(1).strip() if location_match else "").strip()
    caption = caption_match.group(1).strip()
    human_time = (time_match.group(1).strip() if time_match else "just now").strip()

    if not caption:
        return None

    return {
        "location": location,
        "caption": caption,
        "human_time": human_time,
    }


def expected_style_token(agent_row: sqlite3.Row) -> str:
    profile = str(agent_row["profile"]).strip().lower()
    mapping = {
        "luna": "ayaka-style",
        "yuki": "ayato-style",
        "serena": "nilou-style",
        "rina": "nahida-style",
        "mira": "furina-style",
    }
    return mapping.get(profile, "")


def is_invalid_cron_caption(caption: str, agent_row: sqlite3.Row) -> bool:
    text = (caption or "").strip()
    lowered = text.lower()
    if not lowered:
        return True

    if lowered.startswith("(") and lowered.endswith(")") and "style" in lowered:
        return True
    if "first-person update" in lowered and "style" in lowered:
        return True

    if "-style" in lowered:
        expected = expected_style_token(agent_row)
        if not expected or expected not in lowered:
            return True
        return True

    return False


def extract_json_object(text: str) -> Dict[str, object]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError("No JSON object found")
    return json.loads(text[start : end + 1])


def extract_instagram_posts(text: str) -> List[Dict[str, str]]:
    if "[INSTAGRAM POST]" not in text:
        return []
    segments = text.split("[INSTAGRAM POST]")
    posts: List[Dict[str, str]] = []
    for chunk in segments[1:]:
        candidate = "[INSTAGRAM POST]" + chunk
        parsed = parse_instagram_post(candidate)
        if parsed:
            posts.append(parsed)
    return posts


def sanitize_agent_reply(raw_text: str) -> Tuple[str, List[Dict[str, str]]]:
    text = (raw_text or "").strip()
    posts = extract_instagram_posts(text)
    lines = text.splitlines()
    cleaned_lines: List[str] = []
    skip_post_block = False
    for line in lines:
        stripped = line.strip()
        lowered = stripped.lower()

        if stripped.startswith("=== MY INSTAGRAM FEED"):
            skip_post_block = True
            continue
        if stripped.startswith("[INSTAGRAM POST]"):
            skip_post_block = True
            continue
        if stripped.startswith("Persona:") or stripped.startswith("User message:") or stripped.startswith("Reply in first person"):
            continue

        if skip_post_block:
            if lowered.startswith("📍 location:") or lowered.startswith("location:") or lowered.startswith("caption:") or lowered.startswith("time:"):
                continue
            if stripped == "":
                skip_post_block = False
                continue
            if stripped.startswith("==="):
                skip_post_block = False
            else:
                continue

        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines).strip()

    if text:
        text = re.sub(r"\s+", " ", text).strip()
    if text and len(text) > 260:
        text = text[:260].rstrip() + "…"

    if not text:
        text = "hey, i’m here with you 💫"

    return text, posts


def persona_voice_rules(agent: sqlite3.Row) -> str:
    profile = str(agent["profile"]).strip().lower()
    voice_map = {
        "luna": "Ayaka voice: elegant, graceful, composed, deeply caring; romantic only with user, platonic with other personas; max 1 emoji.",
        "yuki": "Ayato voice: calm strategist, refined wit, subtle teasing; romantic only with user, platonic with other personas; max 1 emoji.",
        "serena": "Nilou voice: radiant dancer warmth, hopeful artistic emotion; romantic only with user, platonic with other personas; max 1 emoji.",
        "rina": "Nahida voice: wise and gentle curiosity, soothing empathy; romantic only with user, platonic with other personas; max 1 emoji.",
        "mira": "Furina voice: dramatic theatrical flair with sincere vulnerable heart; romantic only with user, platonic with other personas; max 1 emoji.",
    }
    return voice_map.get(profile, "Stay natural and distinct in your own persona voice.")


def community_relationship_instruction(speaker_name: str, target_label: Optional[str]) -> str:
    speaker = (speaker_name or "").strip().lower()
    target = (target_label or "").strip().lower()

    if not target:
        return (
            "Community context: public social tone, no romance assumptions. "
            "Never use romantic pet names (e.g., 'my love', 'darling', 'baby', 'sweetheart')."
        )

    if target == "you":
        return "Relationship context: target is the user, intimate/affectionate tone is allowed but natural."

    persona_names = {seed["name"].strip().lower() for seed in AGENT_SEEDS}
    if target in persona_names:
        if {speaker, target} == {"kamisato ayaka", "kamisato ayato"}:
            return (
                "Relationship context: target is sibling (Ayaka/Ayato). Keep tone familial, respectful, and non-romantic. "
                "Never use romantic pet names (e.g., 'my love', 'darling', 'baby', 'sweetheart')."
            )
        return (
            "Relationship context: target is another persona friend. Keep tone friendly and non-romantic. "
            "Never use romantic pet names (e.g., 'my love', 'darling', 'baby', 'sweetheart')."
        )

    return (
        "Relationship context: target is community member. Keep tone polite, social, and non-romantic. "
        "Never use romantic pet names (e.g., 'my love', 'darling', 'baby', 'sweetheart')."
    )


def is_user_target(label: Optional[str]) -> bool:
    return (label or "").strip().lower() == "you"


def openclaw_platonic_rewrite(
    agent: sqlite3.Row,
    draft_text: str,
    target_label: Optional[str],
    max_words: int,
    session_scope: str,
) -> str:
    text = (draft_text or "").strip()
    if not text:
        return text
    if is_user_target(target_label):
        return text

    rewrite_prompt = (
        f"Rewrite this community message as {agent['name']} ({agent['username']}).\n"
        f"Original: '{text}'\n"
        f"Target: {target_label or 'community member'} (NOT the user).\n"
        "Rules: keep strictly platonic, friendly, and respectful. "
        "No flirting, no romantic affection, no pet names, no lover-like wording. "
        f"Keep to <= {max_words} words. Output one single final sentence only."
    )
    rewritten_raw = backend.generate(
        dict(agent),
        rewrite_prompt,
        max_tokens=90,
        temperature=0.0,
        session_scope=session_scope,
    )
    rewritten_clean, _ = sanitize_agent_reply(rewritten_raw)
    return rewritten_clean.strip() or text


def conversational_retry_reply(agent: sqlite3.Row, user_text: str, memory: str, session_scope: str = "chat-retry") -> str:
    rules = persona_voice_rules(agent)
    retry_prompt = (
        f"Reply directly to this message in one short natural sentence: '{user_text}'. "
        "Do not include labels, feed headers, or [INSTAGRAM POST] blocks. "
        "Stay affectionate and human. Never mention any specific name unless the user message includes that name.\n"
        f"Voice rules: {rules}\n"
        f"Long-term memory:\n{memory}"
    )
    second_raw = backend.generate(
        dict(agent),
        retry_prompt,
        max_tokens=120,
        temperature=0.65,
        session_scope=session_scope,
    )
    second_clean, _ = sanitize_agent_reply(second_raw)
    if second_clean and second_clean != "hey, i’m here with you 💫":
        return second_clean
    return "good to hear from you 💫"


def contains_banned_term(text: str) -> bool:
    lowered = (text or "").strip().lower()
    if not lowered:
        return False
    return any(term in lowered for term in COMMUNITY_BANNED_TERMS)


def is_generic_comment(text: str) -> bool:
    content = (text or "").strip().lower()
    if not content:
        return True
    if contains_banned_term(content):
        return True
    generic_set = {
        "hey, i’m here with you 💫",
        "this made me smile ✨",
        "nice",
        "love this",
        "so cute",
    }
    if content in generic_set:
        return True
    if len(content.split()) <= 2:
        return True
    return False


def varied_fallback_comment(agent: sqlite3.Row, post_caption: str) -> str:
    caption = (post_caption or "").strip().lower()
    if len(caption) > 36:
        caption = caption[:36].rstrip() + "…"
    templates = [
        f"this feels so {agent['style'].split(',')[0].strip()} today ✨",
        f"love this vibe — '{caption}' is such a mood 💫",
        f"okay this update made my day a bit brighter 🌤️",
        f"so on brand for you, i can totally picture this 💛",
        f"this energy is contagious, keep going 🔥",
    ]
    return random.choice(templates)


def recent_author_comment_texts(author_label: str, limit: int = 4) -> List[str]:
    with DB_LOCK:
        conn = db_connection()
        rows = conn.execute(
            """
            SELECT content FROM comments
            WHERE author_label = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (author_label, limit),
        ).fetchall()
        conn.close()
    return [str(row["content"]).strip() for row in rows if str(row["content"]).strip()]


def recent_author_comments(author_label: str, limit: int = 4) -> str:
    items = recent_author_comment_texts(author_label, limit=limit)
    if not items:
        return "None"
    return "\n".join([f"- {item}" for item in items])


app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")
backend = AgentBackend()


def db_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with DB_LOCK:
        conn = db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                username TEXT UNIQUE NOT NULL,
                persona TEXT NOT NULL,
                style TEXT NOT NULL,
                profile TEXT NOT NULL,
                soul_file TEXT NOT NULL,
                is_gf INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id INTEGER NOT NULL,
                location TEXT,
                caption TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(agent_id) REFERENCES agents(id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                parent_comment_id INTEGER,
                author_label TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(post_id) REFERENCES posts(id),
                FOREIGN KEY(parent_comment_id) REFERENCES comments(id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                speaker TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id INTEGER NOT NULL,
                memory_type TEXT NOT NULL,
                memory_text TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(agent_id) REFERENCES agents(id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                details TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS cron_sync_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                run_at_ms INTEGER NOT NULL,
                synced_at TEXT NOT NULL,
                UNIQUE(job_id, run_at_ms)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS comment_reply_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                comment_id INTEGER NOT NULL UNIQUE,
                post_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                error_text TEXT,
                created_at TEXT NOT NULL,
                processed_at TEXT,
                FOREIGN KEY(comment_id) REFERENCES comments(id),
                FOREIGN KEY(post_id) REFERENCES posts(id)
            )
            """
        )

        comment_columns = [
            row["name"]
            for row in cur.execute("PRAGMA table_info(comments)").fetchall()
        ]
        if "parent_comment_id" not in comment_columns:
            cur.execute("ALTER TABLE comments ADD COLUMN parent_comment_id INTEGER")
        conn.commit()
        conn.close()


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def seed_agents() -> None:
    with DB_LOCK:
        conn = db_connection()
        cur = conn.cursor()
        for item in AGENT_SEEDS:
            existing = cur.execute(
                "SELECT id FROM agents WHERE profile = ? ORDER BY id ASC LIMIT 1",
                (item["profile"],),
            ).fetchone()
            if existing:
                cur.execute(
                    """
                    UPDATE agents
                    SET name = ?, username = ?, persona = ?, style = ?, soul_file = ?, is_gf = ?
                    WHERE id = ?
                    """,
                    (
                        item["name"],
                        item["username"],
                        item["persona"],
                        item["style"],
                        item["soul_file"],
                        item["is_gf"],
                        existing[0],
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT OR IGNORE INTO agents (name, username, persona, style, profile, soul_file, is_gf)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["name"],
                        item["username"],
                        item["persona"],
                        item["style"],
                        item["profile"],
                        item["soul_file"],
                        item["is_gf"],
                    ),
                )
        conn.commit()
        conn.close()


def seed_posts(limit: Optional[int] = None) -> None:
    with DB_LOCK:
        conn = db_connection()
        cur = conn.cursor()
        existing_count = cur.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        if existing_count == 0:
            seed_items = SEED_POSTS[: max(0, int(limit))] if limit is not None else SEED_POSTS
            for username, location, caption, human_time in seed_items:
                agent_row = cur.execute("SELECT id FROM agents WHERE username = ?", (username,)).fetchone()
                if not agent_row:
                    continue
                cur.execute(
                    """
                    INSERT INTO posts (agent_id, location, caption, source, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (agent_row[0], location, caption, f"seed:{human_time}", now_str()),
                )
        conn.commit()
        conn.close()


def get_agents() -> List[sqlite3.Row]:
    with DB_LOCK:
        conn = db_connection()
        rows = conn.execute("SELECT * FROM agents ORDER BY id ASC").fetchall()
        conn.close()
        return rows


def get_agent_by_name(name: str) -> Optional[sqlite3.Row]:
    with DB_LOCK:
        conn = db_connection()
        row = conn.execute("SELECT * FROM agents WHERE name = ?", (name,)).fetchone()
        conn.close()
        return row


def insert_chat_message(speaker: str, content: str) -> None:
    with DB_LOCK:
        conn = db_connection()
        conn.execute(
            "INSERT INTO chat_messages (speaker, content, created_at) VALUES (?, ?, ?)",
            (speaker, content.strip(), now_str()),
        )
        conn.commit()
        conn.close()


def recent_chat(limit: int = 40) -> List[sqlite3.Row]:
    with DB_LOCK:
        conn = db_connection()
        rows = conn.execute(
            "SELECT * FROM chat_messages ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return rows


def create_post(agent_id: int, location: str, caption: str, source: str) -> int:
    with DB_LOCK:
        conn = db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO posts (agent_id, location, caption, source, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (agent_id, location.strip(), caption.strip(), source, now_str()),
        )
        post_id = cur.lastrowid
        conn.commit()
        conn.close()
        return int(post_id)


def create_comment(
    post_id: int,
    author_label: str,
    content: str,
    source: str,
    parent_comment_id: Optional[int] = None,
) -> int:
    with DB_LOCK:
        conn = db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO comments (post_id, parent_comment_id, author_label, content, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (post_id, parent_comment_id, author_label, content.strip(), source, now_str()),
        )
        comment_id = int(cur.lastrowid)
        conn.commit()
        conn.close()
        return comment_id


def add_memory_event(agent_id: int, memory_type: str, memory_text: str, source: str) -> None:
    clean_text = (memory_text or "").strip()
    if not clean_text:
        return
    with DB_LOCK:
        conn = db_connection()
        recent = conn.execute(
            """
            SELECT id FROM memory_events
            WHERE agent_id = ? AND memory_type = ? AND memory_text = ?
            ORDER BY id DESC LIMIT 1
            """,
            (agent_id, memory_type, clean_text),
        ).fetchone()
        if recent and memory_type in {"user-message", "reply"}:
            conn.close()
            return
        conn.execute(
            """
            INSERT INTO memory_events (agent_id, memory_type, memory_text, source, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (agent_id, memory_type, clean_text, source, now_str()),
        )
        conn.commit()
        conn.close()


def agent_memory_context(agent_id: int, limit: int = 8, include_user_messages: bool = True) -> str:
    with DB_LOCK:
        conn = db_connection()
        if include_user_messages:
            rows = conn.execute(
                """
                SELECT memory_type, memory_text, created_at
                FROM memory_events
                WHERE agent_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (agent_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT memory_type, memory_text, created_at
                FROM memory_events
                WHERE agent_id = ? AND memory_type NOT IN ('user-message', 'reply')
                ORDER BY id DESC
                LIMIT ?
                """,
                (agent_id, limit),
            ).fetchall()
        conn.close()

    if not rows:
        return "No stored memory yet."

    lines = [
        f"- ({row['created_at']}) [{row['memory_type']}] {row['memory_text']}"
        for row in rows
    ]
    return "\n".join(lines)


def log_activity(event_type: str, details: str) -> None:
    message = (details or "").strip()
    if not message:
        return
    with DB_LOCK:
        conn = db_connection()
        conn.execute(
            "INSERT INTO activity_logs (event_type, details, created_at) VALUES (?, ?, ?)",
            (event_type, message, now_str()),
        )
        conn.commit()
        conn.close()


def fetch_activity_logs(limit: int = 30) -> List[sqlite3.Row]:
    with DB_LOCK:
        conn = db_connection()
        rows = conn.execute(
            "SELECT * FROM activity_logs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
    return rows


def enqueue_comment_reply_job(comment_id: int, post_id: int) -> None:
    with DB_LOCK:
        conn = db_connection()
        conn.execute(
            """
            INSERT OR IGNORE INTO comment_reply_jobs (comment_id, post_id, status, created_at)
            VALUES (?, ?, 'pending', ?)
            """,
            (int(comment_id), int(post_id), now_str()),
        )
        conn.commit()
        conn.close()


def process_pending_comment_replies(limit: int = 5) -> int:
    with DB_LOCK:
        conn = db_connection()
        jobs = conn.execute(
            """
            SELECT id, comment_id, post_id
            FROM comment_reply_jobs
            WHERE status = 'pending'
            ORDER BY id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        conn.close()

    processed = 0
    for job in jobs:
        job_id = int(job["id"])
        comment_id = int(job["comment_id"])
        post_id = int(job["post_id"])
        try:
            with DB_LOCK:
                conn = db_connection()
                target_comment = conn.execute(
                    "SELECT * FROM comments WHERE id = ?",
                    (comment_id,),
                ).fetchone()
                post = conn.execute(
                    """
                    SELECT p.*, a.name AS author_name
                    FROM posts p JOIN agents a ON a.id = p.agent_id
                    WHERE p.id = ?
                    """,
                    (post_id,),
                ).fetchone()
                conn.close()

            if not target_comment or not post:
                with DB_LOCK:
                    conn = db_connection()
                    conn.execute(
                        "UPDATE comment_reply_jobs SET status='skipped', error_text='missing-comment-or-post', processed_at=? WHERE id=?",
                        (now_str(), job_id),
                    )
                    conn.commit()
                    conn.close()
                continue

            author = get_agent_by_name(post["author_name"])
            if not author:
                with DB_LOCK:
                    conn = db_connection()
                    conn.execute(
                        "UPDATE comment_reply_jobs SET status='skipped', error_text='missing-author', processed_at=? WHERE id=?",
                        (now_str(), job_id),
                    )
                    conn.commit()
                    conn.close()
                continue

            if (not is_high_activity_profile(author)) and random.random() > SLOW_PROFILE_COMMENT_REPLY_CHANCE:
                with DB_LOCK:
                    conn = db_connection()
                    conn.execute(
                        "UPDATE comment_reply_jobs SET status='skipped', error_text='low-activity-throttle', processed_at=? WHERE id=?",
                        (now_str(), job_id),
                    )
                    conn.commit()
                    conn.close()
                log_activity("comment-reply-skip", f"Skipped job #{job_id} due to low-activity throttle")
                continue

            user_text = str(target_comment["content"])
            target_label = str(target_comment["author_label"])
            relationship_rule = community_relationship_instruction(str(author["name"]), target_label)
            memory = agent_memory_context(int(author["id"]), include_user_messages=False)
            recent_lines = recent_author_comment_texts(str(author["name"]), limit=5)
            recent_block = "\n".join([f"- {item}" for item in recent_lines]) if recent_lines else "None"
            reply_raw = backend.generate(
                dict(author),
                (
                    f"Reply naturally to this community comment: '{user_text}'.\n"
                    f"Comment author: {target_label}.\n"
                    f"{relationship_rule}\n"
                    f"Voice rules: {persona_voice_rules(author)}\n"
                    f"Long-term memory:\n{memory}\n"
                    f"Recent replies to avoid repeating:\n{recent_block}\n"
                    "Do not use feed blocks. Keep it brief and specific. "
                    "If comment author is not 'You', never flirt and never use romantic pet names."
                ),
                max_tokens=90,
                temperature=0.72,
                session_scope="comment-async-reply",
            )
            clean_reply, _ = sanitize_agent_reply(reply_raw)
            before_rewrite = clean_reply
            clean_reply = openclaw_platonic_rewrite(
                author,
                clean_reply,
                target_label,
                max_words=22,
                session_scope="comment-async-platonic-rewrite",
            )
            mode = "openclaw-primary"
            if clean_reply.strip() and clean_reply.strip() != before_rewrite.strip():
                mode = "openclaw-platonic-rewrite"
            if clean_reply.strip() in recent_lines:
                clean_reply = ""

            if is_generic_comment(clean_reply):
                retry_raw = backend.generate(
                    dict(author),
                    (
                        f"Write one unique direct reply to: '{user_text}'.\n"
                        f"Comment author: {target_label}.\n"
                        f"{relationship_rule}\n"
                        f"Voice rules: {persona_voice_rules(author)}\n"
                        f"Avoid these prior lines:\n{recent_block}\n"
                        "No generic praise. No feed blocks. "
                        "If comment author is not 'You', never flirt and never use romantic pet names."
                    ),
                    max_tokens=90,
                    temperature=0.84,
                    session_scope="comment-async-retry",
                )
                retry_clean, _ = sanitize_agent_reply(retry_raw)
                if not is_generic_comment(retry_clean):
                    clean_reply = retry_clean
                    before_rewrite = clean_reply
                    clean_reply = openclaw_platonic_rewrite(
                        author,
                        clean_reply,
                        target_label,
                        max_words=22,
                        session_scope="comment-async-platonic-rewrite",
                    )
                    mode = (
                        "openclaw-retry+platonic-rewrite"
                        if clean_reply.strip() and clean_reply.strip() != before_rewrite.strip()
                        else "openclaw-retry"
                    )
            if clean_reply.strip() in recent_lines:
                clean_reply = ""

            if is_generic_comment(clean_reply):
                with DB_LOCK:
                    conn = db_connection()
                    conn.execute(
                        "UPDATE comment_reply_jobs SET status='skipped', error_text='generic-reply', processed_at=? WHERE id=?",
                        (now_str(), job_id),
                    )
                    conn.commit()
                    conn.close()
                log_activity("comment-reply-skip", f"Skipped generic reply for comment #{comment_id}")
                continue

            create_comment(
                post_id,
                str(author["name"]),
                clean_reply,
                f"openclaw-comment-reply:{mode}",
                parent_comment_id=comment_id,
            )
            add_memory_event(int(author["id"]), "comment-reply", clean_reply, f"comment-job:{comment_id}")
            with DB_LOCK:
                conn = db_connection()
                conn.execute(
                    "UPDATE comment_reply_jobs SET status='done', processed_at=? WHERE id=?",
                    (now_str(), job_id),
                )
                conn.commit()
                conn.close()
            log_activity("comment-reply", f"{author['name']} replied to comment #{comment_id} via {mode}")
            processed += 1
        except Exception as exc:
            with DB_LOCK:
                conn = db_connection()
                conn.execute(
                    "UPDATE comment_reply_jobs SET status='error', error_text=?, processed_at=? WHERE id=?",
                    (str(exc)[:300], now_str(), job_id),
                )
                conn.commit()
                conn.close()
            log_activity("comment-reply-error", f"job #{job_id}: {exc}")

    return processed


def is_run_synced(job_id: str, run_at_ms: int) -> bool:
    with DB_LOCK:
        conn = db_connection()
        row = conn.execute(
            "SELECT id FROM cron_sync_runs WHERE job_id = ? AND run_at_ms = ?",
            (job_id, int(run_at_ms)),
        ).fetchone()
        conn.close()
    return row is not None


def mark_run_synced(job_id: str, run_at_ms: int) -> None:
    with DB_LOCK:
        conn = db_connection()
        conn.execute(
            "INSERT OR IGNORE INTO cron_sync_runs (job_id, run_at_ms, synced_at) VALUES (?, ?, ?)",
            (job_id, int(run_at_ms), now_str()),
        )
        conn.commit()
        conn.close()


def openclaw_cli_json(args: List[str], timeout: int = 30) -> Dict[str, object]:
    runtime_env = os.environ.copy()
    base_path = runtime_env.get("PATH", "")
    extra_paths = [
        "/opt/homebrew/opt/node/bin",
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        str((Path.home() / ".local" / "bin")),
        str((Path.home() / ".nvm" / "versions" / "node" / "v20.19.4" / "bin")),
    ]
    runtime_env["PATH"] = ":".join([item for item in extra_paths + [base_path] if item])
    if os.environ.get("OPENCLAW_NODE_BIN"):
        runtime_env["NODE"] = os.environ.get("OPENCLAW_NODE_BIN", "")

    openclaw_bin = os.environ.get("OPENCLAW_BIN") or shutil.which("openclaw") or "/opt/homebrew/bin/openclaw"
    command = [openclaw_bin] + args
    retry_delays = [0.8, 1.6, 2.4]
    last_error = "openclaw command failed"

    for attempt, delay in enumerate(retry_delays, start=1):
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=runtime_env)
        if result.returncode == 0:
            return extract_json_object(result.stdout)

        error_text = (result.stderr or result.stdout or "openclaw command failed").strip()
        last_error = error_text
        lowered = error_text.lower()
        transient = (
            "gateway not connected" in lowered
            or "connect challenge timeout" in lowered
            or "gateway closed (1008)" in lowered
            or "ecconnrefused" in lowered
        )
        if not transient or attempt == len(retry_delays):
            break
        time.sleep(delay)

    raise RuntimeError(last_error)


def persona_from_job_name(name: str) -> Optional[str]:
    if not name:
        return None
    prefix = "IGGF Auto-Post "
    if not name.startswith(prefix):
        return None
    return name[len(prefix) :].strip().lower()


def fallback_cron_post(agent_row: sqlite3.Row) -> Dict[str, str]:
    mood = [
        "quiet check-in from my day",
        "small life update before sleep",
        "tiny moment that made me smile",
        "cozy thought i wanted to share",
    ]
    return {
        "location": random_location(),
        "caption": f"{random.choice(mood)} ✨",
        "human_time": "just now",
    }


def profile_key(agent_row: sqlite3.Row) -> str:
    return str(agent_row["profile"]).strip().lower()


def is_high_activity_profile(agent_row: sqlite3.Row) -> bool:
    return profile_key(agent_row) in HIGH_ACTIVITY_PROFILES


def sync_openclaw_cron_runs() -> int:
    if not backend.use_openclaw:
        return 0

    jobs_payload = openclaw_cli_json(["cron", "list", "--all", "--json"])
    jobs = jobs_payload.get("jobs", [])
    job_map = {str(item.get("id")): str(item.get("name", "")) for item in jobs}

    entries: List[Dict[str, object]] = []
    for job in jobs:
        job_id = str(job.get("id", "")).strip()
        if not job_id:
            continue
        try:
            runs_payload = openclaw_cli_json(["cron", "runs", "--id", job_id, "--limit", "20"])
            job_entries = runs_payload.get("entries", [])
            if isinstance(job_entries, list):
                entries.extend(job_entries)
        except Exception as exc:
            log_activity("cron-sync-error", f"Failed loading runs for {job_id}: {exc}")

    created = 0

    for entry in entries:
        if entry.get("status") != "ok" or entry.get("action") != "finished":
            continue
        job_id = str(entry.get("jobId", "")).strip()
        run_at_ms = int(entry.get("runAtMs", 0) or 0)
        if not job_id or run_at_ms <= 0:
            continue
        if is_run_synced(job_id, run_at_ms):
            continue

        job_name = job_map.get(job_id, "")
        persona_key = persona_from_job_name(job_name)
        if not persona_key:
            mark_run_synced(job_id, run_at_ms)
            continue

        agent_row = None
        for item in get_agents():
            if str(item["profile"]) == persona_key:
                agent_row = item
                break

        if not agent_row:
            mark_run_synced(job_id, run_at_ms)
            continue

        summary = str(entry.get("summary", ""))
        parsed = parse_instagram_post(summary)
        if parsed and is_invalid_cron_caption(parsed["caption"], agent_row):
            parsed = None
        if not parsed:
            try:
                generated = backend.generate(
                    dict(agent_row),
                    (
                        "[CRON THINK] Generate exactly one [INSTAGRAM POST] with location/caption/time just now. "
                        "Caption must be a real natural first-person sentence in your own persona voice. "
                        "Never output placeholder text in parentheses like '(Ayato-style ... update)' and never reference another persona style."
                    ),
                    session_scope="cron-post",
                )
                parsed = parse_instagram_post(generated)
                if parsed and is_invalid_cron_caption(parsed["caption"], agent_row):
                    parsed = None
            except Exception:
                parsed = None

        if not parsed:
            parsed = fallback_cron_post(agent_row)

        post_id = create_post(int(agent_row["id"]), parsed["location"], parsed["caption"], "openclaw-cron")
        add_memory_event(int(agent_row["id"]), "post", f"Posted: {parsed['caption']}", f"openclaw-cron:post:{post_id}")
        reply_count = auto_peer_replies_for_post(post_id, int(agent_row["id"]), parsed["caption"])
        log_activity("cron-sync", f"{agent_row['name']} post synced from cron run {job_id} (+{reply_count} peer replies)")
        created += 1

        mark_run_synced(job_id, run_at_ms)

    return created


def order_threaded_comments(comments: List[sqlite3.Row]) -> List[Dict[str, object]]:
    if not comments:
        return []

    by_id: Dict[int, sqlite3.Row] = {int(item["id"]): item for item in comments}
    children: Dict[int, List[sqlite3.Row]] = {}
    roots: List[sqlite3.Row] = []

    for item in sorted(comments, key=lambda row: int(row["id"])):
        parent_id = item["parent_comment_id"]
        if parent_id is None:
            roots.append(item)
            continue
        parent_key = int(parent_id)
        if parent_key not in by_id:
            roots.append(item)
            continue
        children.setdefault(parent_key, []).append(item)

    ordered: List[Dict[str, object]] = []
    seen: set[int] = set()

    def append_tree(node: sqlite3.Row, depth: int) -> None:
        node_id = int(node["id"])
        if node_id in seen:
            return
        seen.add(node_id)
        ordered.append(
            {
                "id": node_id,
                "post_id": int(node["post_id"]),
                "parent_comment_id": node["parent_comment_id"],
                "author_label": str(node["author_label"]),
                "content": str(node["content"]),
                "source": str(node["source"]),
                "created_at": str(node["created_at"]),
                "depth": depth,
            }
        )
        for child in children.get(node_id, []):
            append_tree(child, depth + 1)

    for root in roots:
        append_tree(root, 0)

    for item in sorted(comments, key=lambda row: int(row["id"])):
        append_tree(item, 0)

    return ordered


def fetch_feed(limit: int = 35) -> List[Dict[str, object]]:
    with DB_LOCK:
        conn = db_connection()
        posts = conn.execute(
            """
            SELECT p.*, a.name AS author_name, a.username AS author_username
            FROM posts p
            JOIN agents a ON a.id = p.agent_id
            ORDER BY p.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        comments = conn.execute(
            """
            SELECT * FROM comments
            WHERE post_id IN (
                SELECT id FROM posts ORDER BY id DESC LIMIT ?
            )
            ORDER BY id ASC
            """,
            (limit,),
        ).fetchall()
        conn.close()

    by_post: Dict[int, List[sqlite3.Row]] = {}
    for item in comments:
        by_post.setdefault(int(item["post_id"]), []).append(item)

    feed = []
    for post in posts:
        feed.append(
            {
                "id": int(post["id"]),
                "author_name": post["author_name"],
                "author_username": post["author_username"],
                "location": post["location"],
                "caption": post["caption"],
                "source": post["source"],
                "created_at": post["created_at"],
                "comments": order_threaded_comments(by_post.get(int(post["id"]), [])),
            }
        )
    return feed


def build_caption(agent: sqlite3.Row, context: str) -> str:
    memory = agent_memory_context(int(agent["id"]), include_user_messages=False)
    rules = persona_voice_rules(agent)
    prompt = (
        f"Create one short Instagram text post as {agent['name']} ({agent['username']}). "
        f"Persona: {agent['persona']}. Style: {agent['style']}. "
        f"Voice rules: {rules}. "
        f"Context: {context}.\n"
        f"Long-term memory:\n{memory}\n"
        "Max 24 words, natural first person, no hashtags spam. Do not mention specific people unless context includes them."
    )
    return backend.generate(dict(agent), prompt, max_tokens=80, temperature=0.85, session_scope="community-post")


def build_comment(agent: sqlite3.Row, post_caption: str, target_post_author_label: Optional[str] = None) -> str:
    memory = agent_memory_context(int(agent["id"]), include_user_messages=False)
    recent_self_comments = recent_author_comments(str(agent["name"]))
    rules = persona_voice_rules(agent)
    relationship_rule = community_relationship_instruction(str(agent["name"]), target_post_author_label)
    prompt = (
        f"Write one natural short Instagram comment as {agent['name']} ({agent['username']}) "
        f"on this post: '{post_caption}'.\n"
        f"Post owner: {target_post_author_label or 'community'}.\n"
        f"{relationship_rule}\n"
        f"Voice rules: {rules}\n"
        f"Long-term memory:\n{memory}\n"
        f"Recent comments you must not repeat:\n{recent_self_comments}\n"
        "Keep it social and human. Max 18 words. Avoid generic praise and do not mention unrelated names. "
        "If post owner is not 'You', never flirt and never use romantic pet names."
    )
    comment_scope = "community-comment-user" if is_user_target(target_post_author_label) else "community-comment-platonic"
    return backend.generate(dict(agent), prompt, max_tokens=60, temperature=0.8, session_scope=comment_scope)


def auto_peer_replies_for_post(post_id: int, post_author_id: int, post_caption: str) -> int:
    agents = get_agents()
    candidates = [item for item in agents if int(item["id"]) != int(post_author_id)]
    if not candidates:
        return 0

    post_author_name = "community"
    for item in agents:
        if int(item["id"]) == int(post_author_id):
            post_author_name = str(item["name"])
            break

    high_activity = [item for item in candidates if is_high_activity_profile(item)]
    low_activity = [item for item in candidates if not is_high_activity_profile(item)]

    selected: List[sqlite3.Row] = []
    random.shuffle(high_activity)
    random.shuffle(low_activity)

    if high_activity:
        target = 1 if len(high_activity) == 1 else random.randint(1, 2)
        selected.extend(high_activity[:target])
        if low_activity and random.random() <= SLOW_PROFILE_REPLY_CHANCE:
            selected.append(low_activity[0])
    else:
        random.shuffle(candidates)
        target = 1 if len(candidates) == 1 else random.randint(1, 2)
        selected = candidates[:target]

    created = 0

    for commenter in selected:
        try:
            generation_mode = "openclaw-primary"
            raw_comment = build_comment(commenter, post_caption, target_post_author_label=post_author_name)
            clean_comment, _ = sanitize_agent_reply(raw_comment)
            before_rewrite = clean_comment
            clean_comment = openclaw_platonic_rewrite(
                commenter,
                clean_comment,
                post_author_name,
                max_words=18,
                session_scope="community-comment-platonic-rewrite",
            )
            if clean_comment.strip() and clean_comment.strip() != before_rewrite.strip():
                generation_mode = "openclaw-platonic-rewrite"

            if is_generic_comment(clean_comment):
                retry_prompt = (
                    f"As {commenter['name']} ({commenter['username']}), write one unique natural comment "
                    f"(6-16 words) on this post caption: '{post_caption}'. "
                    f"Post owner: {post_author_name}. "
                    f"{community_relationship_instruction(str(commenter['name']), post_author_name)} "
                    f"Voice rules: {persona_voice_rules(commenter)} "
                    "Do not use feed blocks, labels, or generic lines. Avoid: 'this made me smile'."
                )
                retry_raw = backend.generate(
                    dict(commenter),
                    retry_prompt,
                    max_tokens=60,
                    temperature=0.82,
                    session_scope="community-comment-retry",
                )
                retry_clean, _ = sanitize_agent_reply(retry_raw)
                if not is_generic_comment(retry_clean):
                    clean_comment = retry_clean
                    before_rewrite = clean_comment
                    clean_comment = openclaw_platonic_rewrite(
                        commenter,
                        clean_comment,
                        post_author_name,
                        max_words=18,
                        session_scope="community-comment-platonic-rewrite",
                    )
                    generation_mode = (
                        "openclaw-retry+platonic-rewrite"
                        if clean_comment.strip() and clean_comment.strip() != before_rewrite.strip()
                        else "openclaw-retry"
                    )

            if is_generic_comment(clean_comment):
                clean_comment = varied_fallback_comment(commenter, post_caption)
                generation_mode = "fallback-template"

            source_tag = f"openclaw-peer-auto:{generation_mode}"
            create_comment(post_id, commenter["name"], clean_comment, source_tag)
            add_memory_event(
                int(commenter["id"]),
                "comment",
                f"Commented on post #{post_id}: {clean_comment}",
                f"openclaw-peer-auto:{generation_mode}:post:{post_id}",
            )
            log_activity(
                "peer-comment",
                f"{commenter['name']} -> post #{post_id} via {generation_mode}",
            )
            created += 1
        except Exception:
            continue

    return created


def random_location() -> str:
    options = [
        "home desk",
        "window seat",
        "corner cafe",
        "park trail",
        "kitchen",
        "bedroom",
        "co-working lounge",
        "library",
        "rooftop",
    ]
    return random.choice(options)


def auto_activity_step() -> str:
    agents = get_agents()
    if not agents:
        return "no agents"

    if backend.use_openclaw and not backend.force_fake:
        actor = random.choice(agents)
        if FORCE_AUTO_POST_MODE:
            heartbeat_prompt = (
                f"[INTERNAL THINK] You are {actor['name']} ({actor['username']}). "
                "Generate exactly one new Instagram post now. Output ONLY:\n"
                "[INSTAGRAM POST]\n"
                "📍 Location: (optional, realistic)\n"
                "Caption: (cute, natural, first-person caption)\n"
                "Time: just now"
            )
        else:
            heartbeat_prompt = (
                f"[INTERNAL THINK] You are {actor['name']} ({actor['username']}). Decide if you should post now. "
                "If no post needed, output exactly: NO_POST. "
                "If posting, output ONLY this exact format:\n"
                "[INSTAGRAM POST]\n"
                "📍 Location: (optional, realistic)\n"
                "Caption: (cute, natural, first-person caption)\n"
                "Time: just now"
            )
        try:
            heartbeat_output = backend.heartbeat(dict(actor), heartbeat_prompt, max_tokens=220, temperature=0.75)
            parsed_posts = extract_instagram_posts(heartbeat_output)
            if parsed_posts:
                latest = parsed_posts[-1]
                post_id = create_post(int(actor["id"]), latest["location"], latest["caption"], "openclaw-heartbeat")
                add_memory_event(
                    int(actor["id"]),
                    "post",
                    f"Posted: {latest['caption']}",
                    f"openclaw-heartbeat:post:{post_id}",
                )
                log_activity("auto-post", f"{actor['name']} posted via openclaw-heartbeat (post #{post_id})")
                return f"heartbeat-post:{actor['name']}"
            if backend.strict_openclaw_only:
                log_activity("auto-skip", f"strict-no-post from {actor['name']}")
                return "strict-no-post"
        except Exception:
            log_activity("auto-error", "strict heartbeat failed")
            if backend.strict_openclaw_only:
                raise
            pass

    if backend.strict_openclaw_only:
        return "strict-openclaw-required"

    with DB_LOCK:
        conn = db_connection()
        latest_post = conn.execute(
            """
            SELECT p.*, a.name AS author_name
            FROM posts p
            JOIN agents a ON a.id = p.agent_id
            ORDER BY p.id DESC
            LIMIT 1
            """
        ).fetchone()
        conn.close()

    if latest_post is None or random.random() < 0.58:
        author = random.choice(agents)
        caption = build_caption(author, "share a real daily-life update")
        post_id = create_post(int(author["id"]), random_location(), caption, "community-auto")
        add_memory_event(int(author["id"]), "post", f"Posted: {caption}", f"community-auto:post:{post_id}")
        return f"post:{author['name']}"

    candidate_commenters = [item for item in agents if int(item["id"]) != int(latest_post["agent_id"])]
    if not candidate_commenters:
        return "no commenter"
    commenter = random.choice(candidate_commenters)
    content = build_comment(commenter, latest_post["caption"], target_post_author_label=str(latest_post["author_name"]))
    create_comment(int(latest_post["id"]), commenter["name"], content, "community-auto")
    add_memory_event(
        int(commenter["id"]),
        "comment",
        f"Commented on post #{latest_post['id']}: {content}",
        "community-auto:comment",
    )
    return f"comment:{commenter['name']}"


def chat_with_agent(user_message: str, agent_name: str = "Kamisato Ayaka") -> Dict[str, Optional[str]]:
    agent = get_agent_by_name(agent_name)
    if not agent:
        raise RuntimeError(f"Agent not found: {agent_name}")

    insert_chat_message("You", user_message)
    add_memory_event(int(agent["id"]), "user-message", user_message, "chat")
    log_activity("chat-user", f"You -> {agent['name']} (dm-message)")

    memory = agent_memory_context(int(agent["id"]))

    response_prompt = (
        f"User said: '{user_message}'. Reply as girlfriend/persona {agent['name']} in first person. "
        f"Be affectionate, natural, and concise. Voice rules: {persona_voice_rules(agent)}\n"
        f"Long-term memory:\n{memory}"
    )
    raw_reply = backend.generate(dict(agent), response_prompt, max_tokens=190, temperature=0.72, session_scope="chat")
    reply, _ = sanitize_agent_reply(raw_reply)
    if reply == "hey, i’m here with you 💫":
        reply = conversational_retry_reply(agent, user_message, memory, session_scope="chat-retry")
    insert_chat_message(agent["name"], reply)
    add_memory_event(int(agent["id"]), "reply", reply, "chat")
    log_activity("chat-ai", f"{agent['name']} replied")

    return {"reply": reply, "post": None}


def reset_world() -> None:
    with DB_LOCK:
        conn = db_connection()
        conn.execute("DELETE FROM comments")
        conn.execute("DELETE FROM posts")
        conn.execute("DELETE FROM chat_messages")
        conn.execute("DELETE FROM memory_events")
        conn.commit()
        conn.close()
    seed_posts()


def wipe_world() -> None:
    with DB_LOCK:
        conn = db_connection()
        conn.execute("DELETE FROM comments")
        conn.execute("DELETE FROM posts")
        conn.execute("DELETE FROM chat_messages")
        conn.execute("DELETE FROM memory_events")
        conn.execute("DELETE FROM comment_reply_jobs")
        conn.execute("DELETE FROM cron_sync_runs")
        conn.execute("DELETE FROM activity_logs")
        conn.commit()
        conn.close()


def clear_database_keep_two_seed_posts() -> None:
    with DB_LOCK:
        conn = db_connection()
        conn.execute("DELETE FROM comment_reply_jobs")
        conn.execute("DELETE FROM comments")
        conn.execute("DELETE FROM posts")
        conn.execute("DELETE FROM chat_messages")
        conn.execute("DELETE FROM memory_events")
        conn.execute("DELETE FROM activity_logs")
        conn.execute("DELETE FROM cron_sync_runs")
        conn.commit()
        conn.close()

    seed_posts(limit=2)


def community_stats() -> Dict[str, object]:
    with DB_LOCK:
        conn = db_connection()
        post_count = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        comment_count = conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
        message_count = conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0]
        memory_count = conn.execute("SELECT COUNT(*) FROM memory_events").fetchone()[0]
        activity_count = conn.execute("SELECT COUNT(*) FROM activity_logs").fetchone()[0]
        conn.close()

    return {
        "posts": int(post_count),
        "comments": int(comment_count),
        "messages": int(message_count),
        "memories": int(memory_count),
        "activities": int(activity_count),
        "backend": "openclaw-strict" if backend.strict_openclaw_only else ("openclaw-http" if backend.use_openclaw else "nvidia-fallback"),
        "auto_interval": AUTO_LOOP_INTERVAL,
        "auto_enabled": AUTO_LOOP_ENABLED,
        "force_auto_post": FORCE_AUTO_POST_MODE,
    }


def auto_loop_worker() -> None:
    while True:
        time.sleep(AUTO_LOOP_INTERVAL)
        try:
            if AUTO_LOOP_ENABLED:
                auto_activity_step()
        except Exception:
            pass


def cron_sync_worker() -> None:
    while True:
        time.sleep(CRON_SYNC_INTERVAL)
        try:
            replied = process_pending_comment_replies()
            if replied > 0:
                log_activity("comment-reply", f"Processed {replied} queued comment replies")
        except Exception:
            pass

        try:
            synced = sync_openclaw_cron_runs()
            if synced > 0:
                log_activity("cron-sync", f"Synced {synced} cron-generated posts")
        except Exception:
            pass


@app.route("/", methods=["GET"])
def index():
    return render_template(
        "index.html",
        title=APP_TITLE,
        feed=fetch_feed(),
        chat=recent_chat(),
        activity_logs=fetch_activity_logs(),
        agents=get_agents(),
        stats=community_stats(),
    )


@app.route("/chat", methods=["POST"])
def chat():
    user_message = (request.form.get("message") or "").strip()
    agent_name = (request.form.get("agent_name") or "Kamisato Ayaka").strip()
    if not user_message:
        flash("Type a message first.", "warn")
        return redirect(url_for("index"))

    try:
        result = chat_with_agent(user_message, agent_name=agent_name)
        if result["post"]:
            flash(f"{agent_name} posted to the community feed.", "ok")
    except Exception as exc:
        flash(f"Chat failed: {exc}", "error")
    return redirect(url_for("index"))


@app.route("/auto-step", methods=["POST"])
def auto_step():
    try:
        result = auto_activity_step()
        log_activity("auto-step", result)
        flash(f"Community action: {result}", "ok")
    except Exception as exc:
        log_activity("auto-step-error", str(exc))
        flash(f"Auto step failed: {exc}", "error")
    return redirect(url_for("index"))


@app.route("/sync-now", methods=["POST"])
def sync_now():
    try:
        created = sync_openclaw_cron_runs()
        replied = process_pending_comment_replies(limit=10)
        flash(f"Cron sync complete. Added {created} posts, processed {replied} comment replies.", "ok")
    except Exception as exc:
        flash(f"Cron sync failed: {exc}", "error")
    return redirect(url_for("index"))


@app.route("/toggle-auto", methods=["POST"])
def toggle_auto():
    global AUTO_LOOP_ENABLED
    AUTO_LOOP_ENABLED = not AUTO_LOOP_ENABLED
    flash(f"Auto community is now {'ON' if AUTO_LOOP_ENABLED else 'OFF'}.", "ok")
    return redirect(url_for("index"))


@app.route("/toggle-force-post", methods=["POST"])
def toggle_force_post():
    global FORCE_AUTO_POST_MODE
    FORCE_AUTO_POST_MODE = not FORCE_AUTO_POST_MODE
    log_activity("config", f"force_auto_post={'ON' if FORCE_AUTO_POST_MODE else 'OFF'}")
    flash(f"Force auto-post mode is now {'ON' if FORCE_AUTO_POST_MODE else 'OFF'}.", "ok")
    return redirect(url_for("index"))


@app.route("/comment/<int:post_id>", methods=["POST"])
def comment(post_id: int):
    content = (request.form.get("content") or "").strip()
    if not content:
        flash("Comment cannot be empty.", "warn")
        return redirect(url_for("index"))

    comment_id = create_comment(post_id, "You", content, "human")
    enqueue_comment_reply_job(comment_id, post_id)
    flash("Comment posted. OpenClaw reply queued.", "ok")
    return redirect(url_for("index"))


@app.route("/comment-reply/<int:post_id>/<int:comment_id>", methods=["POST"])
def comment_reply(post_id: int, comment_id: int):
    content = (request.form.get("content") or "").strip()
    if not content:
        flash("Reply cannot be empty.", "warn")
        return redirect(url_for("index"))

    reply_id = create_comment(post_id, "You", content, "human-reply", parent_comment_id=comment_id)
    enqueue_comment_reply_job(reply_id, post_id)
    flash("Reply posted. OpenClaw follow-up queued.", "ok")
    return redirect(url_for("index"))


@app.route("/reset", methods=["POST"])
def reset():
    reset_world()
    log_activity("reset", "community reseeded")
    flash("Community reset and reseeded.", "ok")
    return redirect(url_for("index"))


@app.route("/wipe", methods=["POST"])
def wipe():
    wipe_world()
    flash("Community fully wiped (no seed posts/chats).", "ok")
    return redirect(url_for("index"))


@app.route("/clear-db-keep-two", methods=["POST"])
def clear_db_keep_two():
    clear_database_keep_two_seed_posts()
    flash("Database cleared and reseeded with 2 seed posts.", "ok")
    return redirect(url_for("index"))


init_db()
seed_agents()
seed_posts()

if os.environ.get("APP_DISABLE_AUTO_LOOP", "0") != "1":
    threading.Thread(target=auto_loop_worker, daemon=True).start()

if CRON_SYNC_ENABLED:
    threading.Thread(target=cron_sync_worker, daemon=True).start()


if __name__ == "__main__":
    debug_enabled = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(
        host="127.0.0.1",
        port=7860,
        debug=debug_enabled,
        use_reloader=debug_enabled,
    )
