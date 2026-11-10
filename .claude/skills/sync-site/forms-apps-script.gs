/**
 * everyone.AI website forms -> Google Sheet (one tab per form).
 *
 * This file is the source of the Apps Script bound to the "Website" Google Sheet (shared by
 * Celine; script project "everyone.AI website forms", deployed as greg@everyone.ai). It is
 * kept in the repo so the deployed code can be read and redeployed; editing it here changes
 * nothing until it is pasted there and redeployed.
 *
 * The site's forms overlay (forms-overlay.js, published as docs/eai-forms.js) posts every
 * non-newsletter form as URL-encoded fields, plus:
 *   _form  the tab to write to (chosen from the page's canonical path, see formTabs in
 *          site-config.json)
 *   _page  the page URL, _lang the page language
 *   _fields  the form's field names in page order (e.parameter does not keep it), so new
 *          columns are added in the order the visitor sees the fields
 * A post without a valid email is refused, and every value is capped and cannot run as a
 * formula. There is no honeypot: the forms have no action attribute, so a bot that does not
 * run the page's JavaScript never reaches this URL.
 *
 * The first tab, Summary, counts the submissions of each form (see summary_).
 *
 * Each tab gets a header row on first write: Timestamp, Page, Language, then the form's
 * own fields in the order they arrive. A field not seen before adds a column, so a form
 * change on the site never loses data or needs a script change.
 *
 * Deploy: Deploy > New deployment > Web app, Execute as: Me, Who has access: Anyone.
 * Put the /exec URL in site-config.json "formEndpoint". After editing the code, use
 * Deploy > Manage deployments > Edit > Version: New version, so the /exec URL stays the same.
 */

var TABS = ['Home contact', 'Contact', 'Press', 'Open Letter', 'Coalition', 'Reports', 'Other'];
var FIXED = ['Timestamp', 'Page', 'Language'];
var SUMMARY = 'Summary';
var MAX_LEN = 5000;   // per field, so one oversized post cannot fill the sheet

function doPost(e) {
  var lock = LockService.getScriptLock();
  try {
    var p = (e && e.parameter) || {};
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(p.email || '').trim())) {
      return json_({ result: 'error', message: 'email required' });
    }
    var tab = TABS.indexOf(p._form) >= 0 ? p._form : 'Other';
    lock.waitLock(10000);                                            // two posts must not race on the header row
    var sh = tab_(tab);
    var headers = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
    var order = String(p._fields || '').split(',').filter(function (k) { return k in p; });
    order.concat(Object.keys(p)).forEach(function (k) {
      if (k.charAt(0) !== '_' && headers.indexOf(k) < 0) {
        headers.push(k);
        sh.getRange(1, headers.length).setValue(k).setFontWeight('bold');
      }
    });
    var row = headers.map(function (h) {
      if (h === 'Timestamp') return new Date();
      if (h === 'Page') return clean_(p._page);
      if (h === 'Language') return clean_(p._lang);
      return clean_(p[h]);
    });
    sh.appendRow(row);
    return json_({ result: 'ok' });
  } catch (err) {
    return json_({ result: 'error', message: String(err) });
  } finally {
    try { lock.releaseLock(); } catch (x) {}
  }
}

function doGet() {
  return ContentService.createTextOutput('everyone.AI website forms endpoint is running.');
}

/** Creates every tab with its header row, so the sheet shows its layout before the first post,
 *  and the Summary tab. Run once from the editor (select setupTabs, then Run). Safe to run again. */
function setupTabs() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  TABS.forEach(function (t, i) {                  // insertSheet adds next to the active tab: put them in TABS order
    ss.setActiveSheet(tab_(t));
    ss.moveActiveSheet(i + 2);
  });
  summary_();
}

/** First tab: one line per form with its number of submissions and the date of the last one.
 *  Formulas, so it stays current without any work in doPost. Reuses the default "Sheet1". */
function summary_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(SUMMARY) || ss.getSheetByName('Sheet1') || ss.insertSheet(SUMMARY, 0);
  sh.setName(SUMMARY);
  ss.setActiveSheet(sh);
  ss.moveActiveSheet(1);
  sh.clear();
  var rows = [['Form', 'Submissions', 'Last submission']];
  TABS.forEach(function (t) {
    var ref = "'" + t + "'!A2:A";
    rows.push(['=HYPERLINK("#gid=' + ss.getSheetByName(t).getSheetId() + '","' + t + '")',
               '=COUNTA(' + ref + ')', '=IF(COUNTA(' + ref + ')=0,"",MAX(' + ref + '))']);
  });
  rows.push(['Total', '=SUM(B2:B' + (TABS.length + 1) + ')', '=IF(B' + (TABS.length + 2) + '=0,"",MAX(C2:C' + (TABS.length + 1) + '))']);
  sh.getRange(1, 1, rows.length, 3).setValues(rows);
  sh.getRange(1, 1, 1, 3).setFontWeight('bold');
  sh.getRange(rows.length, 1, 1, 3).setFontWeight('bold');
  sh.getRange(2, 3, rows.length - 1, 1).setNumberFormat('yyyy-mm-dd hh:mm');
  sh.setFrozenRows(1);
  sh.setColumnWidth(1, 160).setColumnWidth(2, 110).setColumnWidth(3, 150);
}

function tab_(name) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(name) || ss.insertSheet(name);
  if (sh.getLastRow() === 0) {
    sh.appendRow(FIXED);
    sh.getRange(1, 1, 1, FIXED.length).setFontWeight('bold');
    sh.setFrozenRows(1);
  }
  return sh;
}

/** Cuts long values and neutralises a leading = + - @ so a submission cannot run as a formula. */
function clean_(v) {
  v = v == null ? '' : String(v).slice(0, MAX_LEN);
  return /^[=+\-@]/.test(v) ? "'" + v : v;
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
