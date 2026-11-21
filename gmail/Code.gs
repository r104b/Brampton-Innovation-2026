/** Master inbox poller. All messages and credentials must be fictional/test-only. */
function pollClientEmails() {
  const props = PropertiesService.getScriptProperties();
  const url = props.getProperty('INGEST_URL');
  const token = props.getProperty('INGEST_TOKEN');
  // Stable label suffix -> server-registered project ID. No repo names in emails.
  const routes = JSON.parse(props.getProperty('CLIENT_ROUTES_JSON') || '{}');
  if (!url || !url.startsWith('https://') || !token) throw new Error('Configure HTTPS ingestion and token');
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(1000)) return;
  try {
    const threads = GmailApp.search('label:SentraContext newer_than:30d', 0, 100);
    for (const thread of threads) {
      const clients = thread.getLabels().map(label => label.getName())
        .filter(name => name.startsWith('SentraContext/'))
        .map(name => name.substring('SentraContext/'.length));
      if (clients.length !== 1 || !routes[clients[0]]) {
        console.log('Skipped an unregistered or ambiguous client label');
        continue;
      }
      const clientId = clients[0];
      for (const message of thread.getMessages()) {
        const result = UrlFetchApp.fetch(url, {
          method: 'post', contentType: 'application/json', muteHttpExceptions: true,
          headers: {Authorization: 'Bearer ' + token, 'X-Sentra-Client-ID': clientId},
          payload: JSON.stringify({
            source_id: message.getId(), project_id: routes[clientId], source_type: 'email',
            subject: message.getSubject(), sender: message.getFrom(),
            received_at: message.getDate().toISOString(), body: message.getPlainBody()
          })
        });
        // Supabase's source ledger is authoritative; replays skip extraction.
        // No content, sender, token, or response body is logged.
        console.log('Ingestion HTTP ' + result.getResponseCode());
      }
    }
  } finally { lock.releaseLock(); }
}

function installTrigger() {
  if (!ScriptApp.getProjectTriggers().some(t => t.getHandlerFunction() === 'pollClientEmails')) {
    ScriptApp.newTrigger('pollClientEmails').timeBased().everyMinutes(5).create();
  }
}
