// Receipt 37063527954 consumed the one owner approval. This entry is retired.
import {pathToFileURL} from 'node:url';
export async function migrateOnce() { throw Error('migration_permanently_retired_receipt_37063527954'); }
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 console.error('MIGRATION_RETIRED_NO_HTTP_NO_RETRY');process.exitCode=1;
}
