#!/usr/bin/env python3
"""Turn study documents into structured notes with Sarvam AI."""

from __future__ import annotations

import argparse
import mimetypes
import os
import re
import sys
import time
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROMPT_PATH = ROOT / "prompts" / "study_notes.md"
MODEL = "sarvam-105b-conversations"
CHUNK_CHARS = 16_000
MAX_CHAT_TOKENS = 4096
TERMINAL_JOB_STATES = {"completed", "partially_completed", "failed", "rejected"}


def load_api_key() -> str:
    """Load SARVAM_API_KEY from the process environment or this project's .env."""
    key = os.environ.get("SARVAM_API_KEY", "").strip()
    if key:
        return key

    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            name, separator, value = line.partition("=")
            if separator and name.strip() == "SARVAM_API_KEY":
                value = value.strip().strip('"').strip("'")
                if value:
                    os.environ["SARVAM_API_KEY"] = value
                    return value

    raise ValueError("SARVAM_API_KEY is missing. Add it to .env or your environment.")


def make_client():
    try:
        from sarvamai import SarvamAI
    except ImportError as exc:
        raise RuntimeError("Sarvam SDK not installed. Run: python -m pip install -r requirements.txt") from exc
    return SarvamAI(api_subscription_key=load_api_key())


def digitise_document(client, path: Path, language: str) -> str:
    mime_type, _ = mimetypes.guess_type(path.name)
    if not mime_type:
        raise ValueError(f"Cannot determine the file type for {path.name}.")

    print(f"Digitising {path.name} with Sarvam Document AI...")
    with path.open("rb") as document:
        job = client.doc_ai.digitise(
            file=[(path.name, document, mime_type)],
            language=language,
            output_format="md",
        )

    deadline = time.monotonic() + 900
    while True:
        status = client.doc_ai.get_status(job_id=job.job_id)
        state = str(status.status).lower()
        if state in TERMINAL_JOB_STATES:
            break
        if time.monotonic() >= deadline:
            raise TimeoutError("Sarvam Document AI did not finish within 15 minutes.")
        time.sleep(5)

    if state not in {"completed", "partially_completed"}:
        raise RuntimeError(f"Document digitisation ended with status: {state}.")

    download = client.doc_ai.get_download_url(job_id=job.job_id)
    with urllib.request.urlopen(download.url, timeout=120) as response:
        archive_bytes = response.read()

    with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
        markdown_files = [
            item for item in archive.infolist()
            if not item.is_dir() and Path(item.filename).suffix.lower() in {".md", ".markdown"}
        ]
        if not markdown_files:
            raise RuntimeError("Sarvam Document AI returned no Markdown output.")
        markdown_file = max(markdown_files, key=lambda item: item.file_size)
        return archive.read(markdown_file).decode("utf-8").strip()


def read_document(client, path: Path, language: str) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8").strip()
    if suffix in {".pdf", ".png", ".jpg", ".jpeg"}:
        return digitise_document(client, path, language)
    raise ValueError("Supported inputs are PDF, PNG, JPG, JPEG, TXT, and Markdown files.")


def split_into_chunks(text: str, limit: int = CHUNK_CHARS) -> list[str]:
    """Split on paragraph boundaries, breaking unusually long paragraphs by words."""
    paragraphs = re.split(r"\n\s*\n", text.strip())
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0

    for paragraph in paragraphs:
        parts: list[str] = []
        if len(paragraph) > limit:
            words = paragraph.split()
            part = ""
            for word in words:
                if part and len(part) + len(word) + 1 > limit:
                    parts.append(part)
                    part = word
                else:
                    part = f"{part} {word}".strip()
            if part:
                parts.append(part)
        else:
            parts = [paragraph]

        for part in parts:
            added_length = len(part) + (2 if current else 0)
            if current and current_length + added_length > limit:
                chunks.append("\n\n".join(current))
                current = []
                current_length = 0
                added_length = len(part)
            current.append(part)
            current_length += added_length

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def request_notes(client, instructions: str, content: str) -> str:
    response = client.chat.completions(
        model=MODEL,
        messages=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": content},
        ],
        max_tokens=MAX_CHAT_TOKENS,
    )
    reply = response.choices[0].message.content
    if not reply:
        raise RuntimeError("Sarvam returned an empty notes response.")
    return reply.strip()


def create_notes(client, instructions: str, document: str, source_name: str) -> str:
    chunks = split_into_chunks(document)
    if not chunks:
        raise ValueError("No readable text was found in the document.")

    if len(chunks) == 1:
        return request_notes(
            client,
            instructions,
            f"Create comprehensive study notes from this source document.\n\n"
            f"Source: {source_name}\n\n{chunks[0]}",
        )

    notes: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        print(f"Creating notes for section {index} of {len(chunks)}...")
        notes.append(
            request_notes(
                client,
                instructions,
                f"Create comprehensive notes for this part of a larger source. Keep all important "
                f"concepts, equations, assumptions, examples, and conclusions. Do not add facts "
                f"that are not in this part.\n\nSource: {source_name}\nPart {index} of {len(chunks)}\n\n{chunk}",
            )
        )

    round_number = 1
    while len(notes) > 1:
        consolidated: list[str] = []
        for start in range(0, len(notes), 4):
            group = notes[start : start + 4]
            if len(group) == 1:
                consolidated.append(group[0])
                continue
            print(f"Consolidating notes (round {round_number})...")
            consolidated.append(
                request_notes(
                    client,
                    instructions,
                    "Synthesize these notes from consecutive parts of the same document. Preserve all "
                    "important concepts, technical details, equations, assumptions, qualifications, "
                    "and conclusions. Remove duplication, connect related ideas, and do not add "
                    "unsupported information. Finish with a concise summary and revision points.\n\n"
                    + "\n\n--- Next part ---\n\n".join(group),
                )
            )
        notes = consolidated
        round_number += 1
    return notes[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create structured study notes from a PDF, image, text, or Markdown file."
    )
    parser.add_argument("document", type=Path, help="PDF, PNG, JPG, JPEG, TXT, or Markdown file")
    parser.add_argument("--output", type=Path, help="Output Markdown file (default: notes/<name>-notes.md)")
    parser.add_argument("--language", default="en-IN", help="Document AI language code for PDFs and images (default: en-IN)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.document.expanduser().resolve()
    if not source.is_file():
        print(f"Input file not found: {source}", file=sys.stderr)
        return 2

    output = args.output.expanduser() if args.output else ROOT / "notes" / f"{source.stem}-notes.md"
    if not output.is_absolute():
        output = Path.cwd() / output

    try:
        client = make_client()
        document = read_document(client, source, args.language)
        instructions = PROMPT_PATH.read_text(encoding="utf-8").strip()
        notes = create_notes(client, instructions, document, source.name)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(notes + "\n", encoding="utf-8")
        print(f"Study notes saved to {output}")
        return 0
    except Exception as exc:
        message = str(exc)
        api_key = os.environ.get("SARVAM_API_KEY", "")
        if api_key:
            message = message.replace(api_key, "[redacted]")
        print(f"Error: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
