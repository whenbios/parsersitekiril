const API_BASE_URL = 'http://localhost:8000';

const INPUT_COLUMNS = ['company_name', 'workua_url'];
const OUTPUT_COLUMNS = [
  'website',
  'email_1',
  'email_2',
  'email_3',
  'general_email',
  'marketing_email',
  'manager_email',
  'telegram_1',
  'telegram_2',
  'telegram_3',
  'whatsapp',
  'viber',
  'main_phone',
  'phone_1',
  'phone_2',
  'phone_3',
  'instagram',
  'facebook',
  'linkedin',
  'other_links',
  'status',
  'error',
  'last_checked',
];

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Contact Enrichment')
    .addItem('Start enrichment', 'startEnrichment')
    .addItem('Check status', 'checkStatus')
    .addToUi();
}

function startEnrichment() {
  const sheet = SpreadsheetApp.getActiveSheet();
  const state = getSheetState_(sheet);
  const rows = sheet.getDataRange().getValues();
  const payloadItems = [];

  for (let rowIndex = 2; rowIndex <= rows.length; rowIndex += 1) {
    const row = rows[rowIndex - 1];
    const workuaUrl = row[state.headerMap.workua_url];
    if (!workuaUrl) {
      continue;
    }

    payloadItems.push({
      row_index: rowIndex,
      company_name: row[state.headerMap.company_name] || '',
      workua_url: workuaUrl,
    });

    sheet.getRange(rowIndex, state.headerMap.status + 1).setValue('queued');
  }

  if (!payloadItems.length) {
    SpreadsheetApp.getUi().alert('No rows with workua_url found.');
    return;
  }

  const response = UrlFetchApp.fetch(`${API_BASE_URL}/jobs/start`, {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify({ items: payloadItems }),
    muteHttpExceptions: true,
  });

  if (response.getResponseCode() >= 300) {
    throw new Error(response.getContentText());
  }

  const data = JSON.parse(response.getContentText());
  PropertiesService.getDocumentProperties().setProperty('CONTACT_ENRICHMENT_JOB_ID', String(data.job_id));
  SpreadsheetApp.getUi().alert(`Enrichment started. Job ID: ${data.job_id}`);
}

function checkStatus() {
  const jobId = PropertiesService.getDocumentProperties().getProperty('CONTACT_ENRICHMENT_JOB_ID');
  if (!jobId) {
    SpreadsheetApp.getUi().alert('No active job ID stored. Run Start enrichment first.');
    return;
  }

  const statusResponse = UrlFetchApp.fetch(`${API_BASE_URL}/jobs/${jobId}/status`, {
    muteHttpExceptions: true,
  });
  if (statusResponse.getResponseCode() >= 300) {
    throw new Error(statusResponse.getContentText());
  }

  const statusData = JSON.parse(statusResponse.getContentText());
  if (statusData.status !== 'completed' && statusData.status !== 'failed') {
    SpreadsheetApp.getUi().alert(`Job ${jobId}: ${statusData.status}`);
    return;
  }

  const resultsResponse = UrlFetchApp.fetch(`${API_BASE_URL}/jobs/${jobId}/results`, {
    muteHttpExceptions: true,
  });
  if (resultsResponse.getResponseCode() >= 300) {
    throw new Error(resultsResponse.getContentText());
  }

  const resultData = JSON.parse(resultsResponse.getContentText());
  writeResults_(SpreadsheetApp.getActiveSheet(), resultData.items);
  SpreadsheetApp.getUi().alert(`Job ${jobId} results written to sheet.`);
}

function getSheetState_(sheet) {
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const requiredHeaders = INPUT_COLUMNS.concat(OUTPUT_COLUMNS);

  const headerMap = {};
  headers.forEach((header, index) => {
    headerMap[String(header).trim()] = index;
  });

  const missingHeaders = requiredHeaders.filter((header) => headerMap[header] === undefined);
  if (missingHeaders.length) {
    throw new Error(`Missing headers: ${missingHeaders.join(', ')}`);
  }

  return { headerMap };
}

function writeResults_(sheet, items) {
  const state = getSheetState_(sheet);

  items.forEach((item) => {
    const rowIndex = item.row_index;
    if (!rowIndex) {
      return;
    }

    OUTPUT_COLUMNS.forEach((columnName) => {
      const value = item[columnName] || '';
      sheet.getRange(rowIndex, state.headerMap[columnName] + 1).setValue(value);
    });
  });
}
