-- Read-only inspection. Does not claim, dispatch, insert or reset a job.
SELECT name, sql FROM sqlite_master WHERE type='table' AND name='test_jobs';
PRAGMA table_info(test_jobs);
SELECT COUNT(*) AS job_count FROM test_jobs;
SELECT state, COUNT(*) AS count FROM test_jobs GROUP BY state;
