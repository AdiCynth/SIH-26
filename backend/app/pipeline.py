import logging
from pathlib import Path

from app.db import SessionLocal
from app.intake import IntakeError, prepare
from app.models import Finding, Scan
from app.reasoning import annotate
from app.scanners import deps_scan, gitleaks_scan, lizard_scan, semgrep_scan
from app.scanners.base import RawFinding
from app.scoring import security_score, vibe_debt_score

log = logging.getLogger(__name__)

SCANNERS = [semgrep_scan, gitleaks_scan, deps_scan, lizard_scan]

_ERROR_MAX = 500


def _error_text(message: str) -> str | None:
    """Single choke point for scan.error so it always fits the String(500) column."""
    return message[:_ERROR_MAX] or None


def run_scan(scan_id: int) -> None:
    """Run one scan end to end. Never raises — failures land in scan.status."""
    session = SessionLocal()
    scan: Scan | None = None
    try:
        scan = session.get(Scan, scan_id)
        if scan is None:
            log.warning("scan %s not found", scan_id)
            return

        try:
            scan.status = "running"
            session.commit()

            with prepare(scan.source_type, scan.source_ref,
                         scan.base_ref, scan.head_ref) as workspace:
                findings, failures = _run_scanners(workspace)

            if len(failures) == len(SCANNERS):
                _fail(session, scan, "; ".join(failures) or "All scanners failed")
                return

            annotations = annotate(findings)
            scan.ai_available = annotations is not None

            for index, raw in enumerate(findings):
                note = annotations[index] if annotations else {}
                session.add(Finding(
                    scan_id=scan.id, tool=raw.tool, severity=raw.severity,
                    category=raw.category, file=raw.file, line=raw.line,
                    message=raw.message, license_id=raw.license_id,
                    ai_explanation=note.get("explanation") or None,
                    ai_fix=note.get("fix") or None,
                ))

            scan.security_score = security_score(findings)
            scan.vibe_debt_score = vibe_debt_score(findings)
            scan.error = _error_text("; ".join(failures))
            scan.status = "done"
            session.commit()
        except IntakeError as exc:
            _fail(session, scan, str(exc))
        except Exception as exc:  # noqa: BLE001 - run_scan must never raise into the background thread
            log.exception("scan %s crashed", scan_id)
            _fail(session, scan, f"Scan failed unexpectedly: {exc}")
    finally:
        # Uploaded zips are written to a NamedTemporaryFile(delete=False) by the API
        # layer; intake.prepare only cleans up its own extraction workspace, so the
        # source file itself would otherwise leak for the process lifetime.
        if scan is not None and scan.source_type == "zip":
            try:
                Path(scan.source_ref).unlink(missing_ok=True)
            except OSError:
                log.warning("could not delete temp upload for scan %s", scan_id)
        session.close()


def _run_scanners(workspace) -> tuple[list[RawFinding], list[str]]:
    findings: list[RawFinding] = []
    failures: list[str] = []
    for scanner in SCANNERS:
        try:
            findings.extend(scanner.scan(workspace.path, workspace.files))
        except Exception as exc:  # noqa: BLE001 - one bad tool must not sink the scan
            log.warning("scanner %s failed: %s", scanner.__name__, exc)
            failures.append(f"{scanner.__name__.split('.')[-1]}: {exc}")
    return findings, failures


def _fail(session, scan: Scan, message: str) -> None:
    scan.status = "failed"
    scan.error = _error_text(message)
    try:
        session.commit()
    except Exception:  # noqa: BLE001 - recording the failure must not itself raise
        log.exception("could not record failure for scan %s", scan.id)
        session.rollback()
