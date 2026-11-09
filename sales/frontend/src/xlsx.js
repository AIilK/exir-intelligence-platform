// ساخت فایل اکسل واقعی (xlsx) بدون کتابخانه: برگه راست‌به‌چپ با فونت Tahoma، سطر عنوان رنگی و ثابت، کادر خانه‌ها،
// جداکننده هزارگان، درصد واقعی، ردیف جمع پررنگ، فیلتر و چند برگه. xlsx یک فایل zip است؛ اینجا بدون فشرده‌سازی (stored) ساخته می‌شود.

const enc = new TextEncoder()

const CRC_TABLE = (() => {
  const t = new Uint32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    t[n] = c >>> 0
  }
  return t
})()
function crc32(bytes) {
  let c = 0xffffffff
  for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8)
  return (c ^ 0xffffffff) >>> 0
}

function zip(files) {
  const parts = []
  const central = []
  let offset = 0
  for (const { name, data } of files) {
    const nameB = enc.encode(name)
    const crc = crc32(data)
    const local = new DataView(new ArrayBuffer(30))
    local.setUint32(0, 0x04034b50, true)
    local.setUint16(4, 20, true)
    local.setUint16(6, 0x0800, true) // نام فایل UTF-8
    local.setUint16(8, 0, true) // stored
    local.setUint32(14, crc, true)
    local.setUint32(18, data.length, true)
    local.setUint32(22, data.length, true)
    local.setUint16(26, nameB.length, true)
    parts.push(new Uint8Array(local.buffer), nameB, data)
    const cen = new DataView(new ArrayBuffer(46))
    cen.setUint32(0, 0x02014b50, true)
    cen.setUint16(4, 20, true)
    cen.setUint16(6, 20, true)
    cen.setUint16(8, 0x0800, true)
    cen.setUint32(16, crc, true)
    cen.setUint32(20, data.length, true)
    cen.setUint32(24, data.length, true)
    cen.setUint16(28, nameB.length, true)
    cen.setUint32(42, offset, true)
    central.push(new Uint8Array(cen.buffer), nameB)
    offset += 30 + nameB.length + data.length
  }
  const cenSize = central.reduce((a, p) => a + p.length, 0)
  const end = new DataView(new ArrayBuffer(22))
  end.setUint32(0, 0x06054b50, true)
  end.setUint16(8, files.length, true)
  end.setUint16(10, files.length, true)
  end.setUint32(12, cenSize, true)
  end.setUint32(16, offset, true)
  return new Blob([...parts, ...central, new Uint8Array(end.buffer)],
    { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
}

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
  // کاراکترهای کنترلی در XML مجاز نیستند
  .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, '')
const colName = (i) => {
  let s = ''
  for (let n = i + 1; n > 0; n = Math.floor((n - 1) / 26)) s = String.fromCharCode(65 + ((n - 1) % 26)) + s
  return s
}

// ---------------------------------------------------------------- سبک‌ها
// هر خانه یک «نقش» (st) و یک «نوع» (k) دارد؛ ترکیب آن‌ها یک سبک می‌شود.
// نقش‌ها: body خانه جدول، total ردیف جمع، head سطر عنوان ستون‌ها، title عنوان برگه، note توضیح، input پارامتر قابل ویرایش
// نوع‌ها: text، int (عدد صحیح با جداکننده)، money (مبلغ بدون اعشار)، dec (یک رقم اعشار)، pct (درصد ۰.۰٪)، pct2 (درصد ۰.۰۰٪)
const FONT = 'Tahoma'
const NUMFMT = { text: 0, int: 3, money: 3, dec: 164, pct: 165, pct2: 166 }
const FONTS = { body: 0, total: 1, head: 2, title: 3, note: 4, input: 1, label: 1 }
const FILLS = { body: 0, total: 3, head: 2, title: 0, note: 0, input: 4, label: 5 }
const BORDERS = { body: 1, total: 2, head: 1, title: 0, note: 0, input: 1, label: 1 }
const ROLES = Object.keys(FONTS)
const KINDS = Object.keys(NUMFMT)
const styleId = (st = 'body', k = 'text') => ROLES.indexOf(st) * KINDS.length + KINDS.indexOf(k) + 1  // ۰ = پیش‌فرض

const STYLES = (() => {
  const xfs = ['<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>']
  for (const st of ROLES) {
    for (const k of KINDS) {
      const wrap = st === 'head'
      const h = st === 'head' ? ' horizontal="center"' : ''
      xfs.push(`<xf numFmtId="${NUMFMT[k]}" fontId="${FONTS[st]}" fillId="${FILLS[st]}" borderId="${BORDERS[st]}" xfId="0" `
        + `applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">`
        + `<alignment vertical="center"${h}${wrap ? ' wrapText="1"' : ''} readingOrder="2"/></xf>`)
    }
  }
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="3"><numFmt numFmtId="164" formatCode="#,##0.0"/><numFmt numFmtId="165" formatCode="0.0%"/><numFmt numFmtId="166" formatCode="0.00%"/></numFmts>
<fonts count="5">
<font><sz val="10"/><color rgb="FF1F2937"/><name val="${FONT}"/><family val="2"/></font>
<font><b/><sz val="10"/><color rgb="FF0F3D38"/><name val="${FONT}"/><family val="2"/></font>
<font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="${FONT}"/><family val="2"/></font>
<font><b/><sz val="13"/><color rgb="FF0F766E"/><name val="${FONT}"/><family val="2"/></font>
<font><sz val="9"/><color rgb="FF6B7280"/><name val="${FONT}"/><family val="2"/></font>
</fonts>
<fills count="6"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF0F766E"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFDDF1EC"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFFF6D5"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFF1F5F9"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="3"><border><left/><right/><top/><bottom/><diagonal/></border>
<border><left style="thin"><color rgb="FFD5DCE3"/></left><right style="thin"><color rgb="FFD5DCE3"/></right><top style="thin"><color rgb="FFD5DCE3"/></top><bottom style="thin"><color rgb="FFD5DCE3"/></bottom><diagonal/></border>
<border><left style="thin"><color rgb="FFD5DCE3"/></left><right style="thin"><color rgb="FFD5DCE3"/></right><top style="medium"><color rgb="FF0F766E"/></top><bottom style="medium"><color rgb="FF0F766E"/></bottom><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="${xfs.length}">${xfs.join('')}</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>`
})()

// ---------------------------------------------------------------- برگه
// خانه: مقدار ساده (عدد / متن) یا شیء {v | f, k, st}؛ f فرمول بدون «=» است و اکسل هنگام باز کردن حسابش می‌کند.
const textLen = (s) => [...String(s)].length * 1.15  // حروف فارسی کمی پهن‌ترند

function sheetXml({ rows, widths: fixed, freezeRow = 0, freezeCol = 0, autoFilter, merges = [], heights = {} }) {
  const n = Math.max(1, ...rows.map((r) => r.length))
  const widths = Array.from({ length: n }, (_, c) => fixed?.[c] ?? 6)
  const auto = !fixed
  const cell = (raw, r, c) => {
    const o = raw && typeof raw === 'object' ? raw : { v: raw }
    const ref = `${colName(c)}${r}`
    const st = o.st || 'body'
    const k = o.k || (typeof o.v === 'number' ? 'dec' : 'text')
    const s = styleId(st, k)
    if (o.f) {
      // مقدار محاسبه‌شده (v) هم ذخیره می‌شود تا پیش‌نمایش‌هایی که فرمول را حساب نمی‌کنند (مثل موبایل) عدد را نشان دهند
      const has = o.v !== '' && o.v != null && (k === 'text' || (typeof o.v === 'number' && Number.isFinite(o.v)))
      if (auto && st !== 'title' && st !== 'note') {
        widths[c] = Math.max(widths[c], k === 'text' ? Math.min(textLen(has ? o.v : '') + 2, 40) || 10
          : has ? Math.min(String(Math.round(Math.abs(o.v))).length * 1.35 + 3, 22) : 14)
      }
      const cached = has ? `<v>${esc(o.v)}</v>` : ''
      return `<c r="${ref}" s="${s}"${k === 'text' ? ' t="str"' : ''}><f>${esc(o.f)}</f>${cached}</c>`
    }
    const v = o.v
    if (v === '' || v == null) return `<c r="${ref}" s="${s}"/>`
    if (typeof v === 'number' && Number.isFinite(v) && k !== 'text') {
      if (auto) widths[c] = Math.max(widths[c], Math.min(String(Math.round(Math.abs(v))).length * 1.35 + 3, 22))
      return `<c r="${ref}" s="${s}"><v>${v}</v></c>`
    }
    if (auto && st !== 'title' && st !== 'note' && st !== 'head') widths[c] = Math.max(widths[c], Math.min(textLen(v) + 2, 50))
    if (auto && st === 'head') widths[c] = Math.max(widths[c], Math.min(textLen(v) / 1.6 + 3, 24))
    return `<c r="${ref}" s="${s}" t="inlineStr"><is><t xml:space="preserve">${esc(v)}</t></is></c>`
  }
  const body = rows.map((row, i) => {
    const r = i + 1
    const ht = heights[r] ? ` ht="${heights[r]}" customHeight="1"` : ''
    return `<row r="${r}"${ht}>${row.map((v, c) => cell(v, r, c)).join('')}</row>`
  }).join('')
  const cols = widths.map((w, c) => `<col min="${c + 1}" max="${c + 1}" width="${Math.round(w + 1)}" customWidth="1"/>`).join('')
  // freezeRow سطر بالا و freezeCol ستون اول (در برگه راست‌به‌چپ = ستون‌های سمت راست) ثابت می‌مانند
  const pane = freezeRow && freezeCol
    ? `<pane xSplit="${freezeCol}" ySplit="${freezeRow}" topLeftCell="${colName(freezeCol)}${freezeRow + 1}" activePane="bottomRight" state="frozen"/>`
    : freezeRow ? `<pane ySplit="${freezeRow}" topLeftCell="A${freezeRow + 1}" activePane="bottomLeft" state="frozen"/>` : ''
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetViews><sheetView rightToLeft="1" workbookViewId="0" zoomScale="100">${pane}</sheetView></sheetViews>
<sheetFormatPr defaultRowHeight="20" customHeight="1"/><cols>${cols}</cols><sheetData>${body}</sheetData>
${autoFilter ? `<autoFilter ref="${autoFilter}"/>` : ''}${merges.length ? `<mergeCells count="${merges.length}">${merges.map((m) => `<mergeCell ref="${m}"/>`).join('')}</mergeCells>` : ''}
<pageMargins left="0.4" right="0.4" top="0.5" bottom="0.5" header="0.3" footer="0.3"/>
<pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/></worksheet>`
}

const safeSheet = (name, i) => (String(name).replace(/[[\]:*?/\\']/g, ' ').slice(0, 31) || `Sheet${i + 1}`)

/**
 * کتاب کار چندبرگه‌ای.
 * sheets: [{name, rows, widths?, freezeRow?, freezeCol?, autoFilter? ('A1:H20'), merges?, heights?}]
 * names: [{name, ref}] نام‌های تعریف‌شده برای فرمول‌ها (ref مثل "'قواعد'!$B$3")
 */
export function buildWorkbook(sheets, names = []) {
  const list = sheets.map((s, i) => ({ ...s, name: safeSheet(s.name, i) }))
  const defined = [
    ...list.map((s, i) => (s.autoFilter
      ? `<definedName name="_xlnm._FilterDatabase" localSheetId="${i}" hidden="1">'${esc(s.name)}'!${s.autoFilter.split(':').map((p) => p.replace(/([A-Z]+)(\d+)/, '$$$1$$$2')).join(':')}</definedName>` : '')),
    ...names.map((d) => `<definedName name="${esc(d.name)}">${esc(d.ref)}</definedName>`),
  ].join('')
  const workbook = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<bookViews><workbookView/></bookViews>
<sheets>${list.map((s, i) => `<sheet name="${esc(s.name)}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`).join('')}</sheets>
${defined ? `<definedNames>${defined}</definedNames>` : ''}
<calcPr calcId="191029" fullCalcOnLoad="1"/>
</workbook>`
  const files = {
    '[Content_Types].xml': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
${list.map((_, i) => `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join('\n')}
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>`,
    '_rels/.rels': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>`,
    'xl/workbook.xml': workbook,
    'xl/_rels/workbook.xml.rels': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
${list.map((_, i) => `<Relationship Id="rId${i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`).join('\n')}
<Relationship Id="rId${list.length + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>`,
    'xl/styles.xml': STYLES,
  }
  list.forEach((s, i) => { files[`xl/worksheets/sheet${i + 1}.xml`] = sheetXml(s) })
  return zip(Object.entries(files).map(([name, s]) => ({ name, data: enc.encode(s) })))
}

/** یک جدول ساده (سطر عنوان + داده) به‌صورت شیء برگه برای buildWorkbook. */
export function tableSheet(headers, rows, sheetName = 'گزارش', { filterRows, totalRow = false, freezeCol = 0 } = {}) {
  const kindOf = (h) => (h.kind === 'dec' || h.kind === 'int' || h.kind === 'text' || NUMFMT[h.kind] != null ? h.kind : 'text')
  const head = headers.map((h) => ({ v: h.label, st: 'head', k: 'text' }))
  const fr = filterRows ?? (totalRow ? rows.length - 1 : rows.length)
  const body = rows.map((row, i) => {
    const st = totalRow && i === rows.length - 1 ? 'total' : 'body'
    return row.map((v, c) => {
      const k = kindOf(headers[c])
      const o = v && typeof v === 'object' ? v : { v }
      // متن در ستون عددی (مثلاً «جمع کل» یا «—») همان متن می‌ماند
      const kk = o.f ? (o.k || k) : typeof o.v === 'number' ? (o.k || k) : 'text'
      return { ...o, k: kk, st: o.st || st }
    })
  })
  return {
    name: sheetName, rows: [head, ...body], freezeRow: 1, freezeCol, heights: { 1: 36 },
    autoFilter: headers.length ? `A1:${colName(headers.length - 1)}${fr + 1}` : undefined,
  }
}

/**
 * headers: [{label, kind}] که kind یکی از 'text' | 'int' | 'dec' | 'money' | 'pct' | 'pct2' است؛ rows: آرایه‌ای از آرایه مقدارها.
 * مقدار یک خانه می‌تواند فرمول باشد: {f: 'SUM(B2:B9)'} (بدون =)؛ اکسل هنگام باز کردن حسابش می‌کند.
 * filterRows: تعداد سطرهای داده زیر فیلتر (سطر جمع پایین جدول بیرون از فیلتر می‌ماند و پررنگ می‌شود).
 * extraSheets / names: برگه‌های بیشتر (مثلاً «قواعد») و نام‌های تعریف‌شده برای فرمول‌ها.
 * freezeCol: تعداد ستون‌های اول که هنگام اسکرول افقی ثابت می‌مانند (مثل نام شعبه و نام فروشنده).
 */
export { colName }
export function buildXlsx(headers, rows, sheetName = 'گزارش', { filterRows, extraSheets = [], names = [], freezeCol = 0 } = {}) {
  const totalRow = filterRows != null && filterRows < rows.length
  return buildWorkbook([tableSheet(headers, rows, sheetName, { filterRows, totalRow, freezeCol }), ...extraSheets], names)
}
