-- Sandbox atomicity probe only; not a production durable ledger.
CREATE TABLE backend_probe_v1 (
 platform TEXT NOT NULL CHECK(platform='test'),
 account_id TEXT NOT NULL CHECK(account_id='test_reference_001'),
 intent_id TEXT NOT NULL CHECK(intent_id='plm-d1-atomicity-20261003-r1'),
 job_id TEXT NOT NULL UNIQUE CHECK(job_id='plm-d1-atomicity-job-001'),
 content_fingerprint TEXT NOT NULL CHECK(content_fingerprint='5bb172915fd10aac8565814c5157a28ded8001e0c8cc5a85317f2d0e2a7feb6b'),
 owner TEXT CHECK(owner IN ('contender_a','contender_b')),
 owner_epoch INTEGER NOT NULL CHECK(typeof(owner_epoch)='integer'),
 fencing_token INTEGER NOT NULL CHECK(typeof(fencing_token)='integer'),
 state TEXT NOT NULL CHECK(state IN ('ready','claimed','succeeded','failed')),
 version INTEGER NOT NULL CHECK(typeof(version)='integer'),
 last_request_id TEXT NOT NULL CHECK(length(last_request_id) BETWEEN 1 AND 96),
 delivery_id TEXT UNIQUE,
 result_id TEXT UNIQUE,
 created_at INTEGER NOT NULL CHECK(typeof(created_at)='integer' AND created_at>0),
 updated_at INTEGER NOT NULL CHECK(typeof(updated_at)='integer' AND updated_at>=created_at),
 PRIMARY KEY(platform,account_id,intent_id),
 CHECK((state='ready' AND version=1 AND owner IS NULL AND owner_epoch=0 AND fencing_token=0 AND delivery_id IS NULL AND result_id IS NULL)
 OR (state='claimed' AND version=2 AND owner IS NOT NULL AND owner_epoch=1 AND fencing_token=1 AND delivery_id IS NULL AND result_id IS NULL)
 OR (state IN ('succeeded','failed') AND version=3 AND owner IS NOT NULL AND owner_epoch=1 AND fencing_token=1 AND delivery_id IS NOT NULL AND result_id IS NOT NULL))
);
CREATE TRIGGER backend_probe_v1_guard BEFORE UPDATE ON backend_probe_v1
WHEN NEW.platform IS NOT OLD.platform OR NEW.account_id IS NOT OLD.account_id
 OR NEW.intent_id IS NOT OLD.intent_id OR NEW.job_id IS NOT OLD.job_id
 OR NEW.content_fingerprint IS NOT OLD.content_fingerprint OR NEW.created_at IS NOT OLD.created_at
 OR NEW.updated_at<OLD.updated_at OR NEW.version!=OLD.version+1
 OR NOT((OLD.state='ready' AND NEW.state='claimed' AND NEW.owner_epoch=1 AND NEW.fencing_token=1)
 OR (OLD.state='claimed' AND NEW.state IN ('succeeded','failed') AND NEW.owner IS OLD.owner
 AND NEW.owner_epoch=OLD.owner_epoch AND NEW.fencing_token=OLD.fencing_token))
BEGIN
 SELECT RAISE(ABORT,'backend_probe_guard');
END;
