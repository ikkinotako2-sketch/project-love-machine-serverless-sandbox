-- OFFLINE PROPOSAL ONLY. No migration authorization. Preserve all stage2 tables.
CREATE TABLE youtube_roundtrip_checkpoint (
 job_id TEXT PRIMARY KEY CHECK(length(job_id) BETWEEN 1 AND 64),
 account_id TEXT NOT NULL CHECK(account_id='youtube_game_001'),
 intent_id TEXT NOT NULL UNIQUE,
 request_sha256 TEXT NOT NULL CHECK(length(request_sha256)=64),
 model TEXT NOT NULL CHECK(model='gemini-3.8-flash'),
 state TEXT NOT NULL CHECK(state IN ('STARTED','COMPLETED','UNKNOWN')),
 script_json TEXT CHECK(script_json IS NULL OR (json_valid(script_json) AND length(script_json)<=65536)),
 script_sha256 TEXT CHECK(script_sha256 IS NULL OR length(script_sha256)=64),
 version INTEGER NOT NULL CHECK(version IN (1,2)),
 CHECK((state='STARTED' AND version=1 AND script_json IS NULL AND script_sha256 IS NULL) OR
 (state='UNKNOWN' AND version=2 AND script_json IS NULL AND script_sha256 IS NULL) OR
 (state='COMPLETED' AND version=2 AND script_json IS NOT NULL AND script_sha256 IS NOT NULL))
);
CREATE TRIGGER youtube_roundtrip_checkpoint_guard BEFORE UPDATE ON youtube_roundtrip_checkpoint
WHEN NEW.job_id IS NOT OLD.job_id OR NEW.account_id IS NOT OLD.account_id OR NEW.intent_id IS NOT OLD.intent_id
 OR NEW.request_sha256 IS NOT OLD.request_sha256 OR NEW.model IS NOT OLD.model
 OR OLD.state!='STARTED' OR NEW.state NOT IN ('COMPLETED','UNKNOWN') OR NEW.version!=OLD.version+1
BEGIN SELECT RAISE(ABORT,'youtube_checkpoint_immutable_or_invalid_transition'); END;
