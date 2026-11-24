// Run: node --test sales/frontend/tests/b2b-workspace.test.cjs
const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { createRequire } = require('node:module')
const deps = createRequire(path.resolve(__dirname, '../../../unified/package.json'))
const React = deps('react')
const { renderToStaticMarkup } = deps('react-dom/server')
const router = deps('react-router-dom')
const ts = deps('typescript')
let response
let chartOptions = []
const lib = {
  useApp: () => ({ unit: 'million', setUnit() {} }), useRkFetch: () => response,
  fmtInt: (n) => String(n ?? '—'), fmtPct: (n) => String(n ?? '—'), fmtMoney: (n) => String(n ?? '—'),
  isNum: (n) => typeof n === 'number', fmtFull: (n) => String(n),
  fmtExact: (n) => String(n ?? '—'), faDigits: (n) => String(n ?? ''),
  UNITS: { million: { div: 1e7, label: 'میلیون تومان' } },
}
const box = ({ title, children, actions, subtitle, label, value, sub }) => React.createElement('section', null, title || label, subtitle, value, sub, actions, children)
const ui = { Card: box, Kpi: (props) => React.createElement('div', { 'data-kpi-type': props.type || 'money' }, box(props)), Loading: () => 'loading', ErrorBox: ({ error }) => error, Empty: () => 'empty',
  Tabs: () => null, MultiSelect: () => null, DataTable: ({ rows }) => React.createElement('div', null, `rows:${rows.length}`) }
const theme = { text: '#fff', surface: '#000', axis: '#555', grid: '#333', dark: true, series: ['red', 'blue', 'green'] }
const charts = {
  useTheme: () => theme,
  Chart: ({ option }) => { const result = option(theme); assert.ok(result.series.length); chartOptions.push(result); return React.createElement('div', null, 'chart') },
  HBar: ({ rows }) => React.createElement('div', null, `bars:${rows.length}`),
  CompareBars: ({ rows, series }) => {
    for (const row of rows) for (const col of series) assert.equal(typeof row[col.key], 'number')
    return React.createElement('div', null, 'comparison')
  },
  Heatmap: ({ rows, vKey }) => { for (const row of rows) assert.equal(typeof row[vKey], 'number'); return 'heatmap' },
  baseOption: () => ({ tooltip: {} }),
}
function load(name) {
  const filename = path.resolve(__dirname, '../src', name)
  const source = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true, target: ts.ScriptTarget.ES2022 },
  }).outputText
  const module = { exports: {} }
  const mockedRequire = (id) => {
    if (id === 'react' || id === 'react/jsx-runtime') return deps(id)
    if (id === 'react-router-dom') return router
    if (id.endsWith('/lib.jsx')) return lib
    if (id.endsWith('/ui.jsx')) return ui
    if (id.endsWith('/Chart.jsx')) return charts
    if (id.endsWith('/ProductMix.jsx')) return { default: load('components/ProductMix.jsx').default, __esModule: true }
    if (id.endsWith('/Layout.jsx')) return { PageHead: box }
    if (id.endsWith('/TreeTable.jsx')) return { TreeTable: ({ nodes }) => `tree:${nodes.length}` }
    if (id.endsWith('/brands.js')) return { brandColor: () => 'red' }
    if (id.endsWith('/iranMap.js')) return load('iranMap.js')
    if (id.endsWith('/SalesDateRange.jsx')) return { __esModule: true, default: () => 'date-range' }
    if (id.endsWith('/DayPicker.jsx')) return { __esModule: true, default: () => null, parseDays: () => [], isDays: () => false }
    if (id === './Rahkaran.jsx') return { BrandDonut: load('pages/Rahkaran.jsx').BrandDonut, BubbleMap: load('pages/Rahkaran.jsx').BubbleMap, CustomerDetail: () => null, ProductFilter: () => null, monthLabel: (m) => m, q: (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v && !Array.isArray(v))).toString() }
    if (id === './Export.jsx') return load('pages/Export.jsx')
    if (id === './RahkaranCompare.jsx' || id === './Reorder.jsx') return { __esModule: true, default: box }
    throw Error(`Unexpected dependency: ${id}`)
  }
  new Function('require', 'module', 'exports', source)(mockedRequire, module, module.exports)
  return module.exports
}
const pages = load('pages/B2BWorkspace.jsx')
test('top 80 includes the crossing customer, stops at exact boundary and ranks quantities independently', () => {
  const customers = [{ key: 'a', net: 60, qty: 1 }, { key: 'b', net: 25, qty: 9 }, { key: 'c', net: 15, qty: 0 }, { key: 'none', net: 0, qty: 0 }]
  const amount = pages.topContributors(customers)
  assert.deepEqual(amount.rows.map((r) => r.key), ['a', 'b'])
  assert.equal(amount.population, 3)
  assert.deepEqual(pages.topContributors(customers, 'qty').rows.map((r) => r.key), ['b'])
  assert.equal(pages.topContributors([{ key: 'a', net: 80 }, { key: 'b', net: 20 }]).rows.length, 1)
  assert.deepEqual(pages.topContributors([]).rows, [])
})
const row = { key: 'A', label: 'A', net: 100, gross: 120, qty: 10, ly_net: 90, returns: 2, req_gross: 200, disc_rate: .1 }
const fixture = {
  kpis: { net: 100, gross: 120, qty: 10, net_cash: 110, returns: 2, cash: 10, mgmt: 5, other_disc: 5, customers_period: 1 },
  options: { brands: ['A'], provinces: ['East'], groups: ['رنگ مو'], customers: [{ code: '1', short: 'rep', brand: 'A' }] },
  periods: [{ value: 'YTD' }], today: '1405/08/20', sale_days: [],
  provinces: [row], customers: [row], categories: [row], brands: [row],
  daily: [{ date: '1405/08/01', net: 100, returns: 2, req_gross: 200 }],
  monthly: [{ month: '1405/08', net: 100, ly_net: 90, qty: 10, ly_qty: 8 }],
  heat: [{ date: '1405/08/01', province: 'East', net: 100, qty: 10 }], heat_req: [],
  goods: { total: { qty: 10 }, nodes: [{ id: 'A', level: 0, label: 'A', net: 100, qty: 10 },
    { id: 'g', parent: 'A', level: 1, label: 'رنگ مو', net: 100, qty: 10 },
    { id: 'p', parent: 'g', level: 2, label: 'product', code: 'p', net: 100, qty: 10 }] },
}
function render(name, url = '/rahkaran/overview') {
  return renderToStaticMarkup(React.createElement(router.MemoryRouter, { initialEntries: [url] }, React.createElement(pages[name])))
}
test('all five pages render; populated chart options evaluate without runtime errors', () => {
  response = { data: fixture, loading: false, error: null }
  for (const name of ['Overview', 'Performance', 'Products', 'Analysis', 'Orders']) assert.ok(render(name).length)
  assert.match(render('Performance'), /جدول عملکرد/)
  assert.match(render('Products'), /chart/)
})
test('new reports render their loading and error states', () => {
  for (const name of ['Overview', 'Performance', 'Products', 'Analysis']) {
    response = { data: null, loading: true, error: null }
    assert.match(render(name), /loading/)
    response = { data: null, loading: false, error: 'SQL unavailable' }
    assert.match(render(name), /SQL unavailable/)
  }
})
test('empty periods render without assuming sales or treemap nodes exist', () => {
  response = { loading: false, error: null, data: { ...fixture, kpis: {}, provinces: [], customers: [], brands: [], categories: [], daily: [], monthly: [], heat: [], goods: { nodes: [], total: {} } } }
  for (const name of ['Overview', 'Performance', 'Products', 'Analysis']) assert.ok(render(name).length)
})
test('overview displays Iran map in both metrics and removes duplicate navigation', () => {
  response = { data: { ...fixture, provinces: [{ ...row, key: 'تهران', net: 123, qty: 456 }] }, loading: false, error: null }
  const amount = render('Overview')
  const quantity = render('Overview', '/rahkaran/overview?metric_map=qty&metric_share=qty')
  assert.match(amount, /سهم برندها از فروش/)
  assert.match(amount, /نرخ تخفیف/)
  assert.match(quantity, /سهم از تعداد فروش/)
  assert.match(amount, /<svg/)
  assert.match(quantity, /<svg/)
  assert.match(amount, />123<\/text>/)
  assert.match(quantity, />456<\/text>/)
  assert.doesNotMatch(quantity, /روند روزانه/)
  for (const name of ['Overview', 'Performance', 'Products', 'Analysis', 'Orders']) assert.doesNotMatch(render(name), /صفحه‌های فروش B2B/)
})
test('map brand chips filter both metrics and chart metrics stay independent', () => {
  response = { loading: false, error: null, data: { ...fixture, provinces: [{ ...row, key: 'تهران', net: 123, qty: 456,
    brands: [{ brand: 'A', net: 45, qty: 67 }] }] } }
  const amount = render('Overview', '/rahkaran/overview?map_brand=A')
  const quantity = render('Overview', '/rahkaran/overview?map_brand=A&metric_map=qty')
  assert.match(amount, />45<\/text>/)
  assert.match(quantity, />67<\/text>/)
  assert.match(quantity, /فروش خالص برندها/)
  assert.match(quantity, /روند ماهانه مبلغی/)
  assert.match(quantity, /برند نقشه ایران/)
  assert.match(quantity, />Total<\/button>/)
  assert.doesNotMatch(quantity, /نمایش همه نمودارها بر اساس/)
  const brandsOnly = render('Overview', '/rahkaran/overview?metric_brands=qty')
  assert.match(brandsOnly, /فروش تعدادی برندها/)
  assert.match(brandsOnly, />123<\/text>/)
})
test('quality focuses on discounts with percent cards, amounts and an additive stacked chart', () => {
  response = { loading: false, error: null, data: { ...fixture,
    kpis: { ...fixture.kpis, gross: 100, cash: 10, mgmt: 5, other_disc: 20, discount: 35,
      disc_rate: .35, cash_rate: .1, mgmt_rate: .05, other_rate: .2 },
    categories: [{ ...row, gross: 100, cash: 10, mgmt: 5, other_disc: 20,
      disc_rate: .35, cash_rate: .1, mgmt_rate: .05, other_rate: .2 }],
  } }
  chartOptions = []
  const html = render('Analysis')
  assert.match(html, /تحلیل کیفیت فروش/)
  assert.doesNotMatch(html, /جدول تحلیل کیفیت فروش/)
  assert.doesNotMatch(html, /مقایسه نمایندگان و دوره‌ها/)
  assert.match(html, /مبلغ: 20 میلیون تومان/)
  assert.equal((html.match(/data-kpi-type="pct"/g) || []).length, 4)
  const stacked = chartOptions.find((option) => option.series.some((series) => series.stack === 'discount'))
  assert.ok(stacked)
  assert.equal(stacked.series.length, 3)
  assert.deepEqual(stacked.series.map((s) => s.data[0]), [.2, .1, .05])
  const tooltip = stacked.tooltip.formatter([{ dataIndex: 0 }])
  assert.match(tooltip, /تخفیف نقدی/)
  assert.match(tooltip, /کل تخفیف/)
})

test('export preview renders merged sections and legacy customer URLs, keeping the original export link', () => {
  const Preview = load('pages/ExportPreview.jsx').default
  const quality = { kpis: { gross: 120, net: 100, cash: 10, mgmt: 5, other_disc: 5 },
    countries: [{ ...row, cash: 10, mgmt: 5, other_disc: 5 }], customers: [], brands: [], categories: [{ ...row, cash: 10, mgmt: 5, other_disc: 5 }] }
  response = { loading: false, error: null, data: { ...fixture, year: '1405', compare_year: '1404', years: ['1405','1404'], current: true,
    kpis: { ...fixture.kpis, pcs: 10 }, countries: [{ ...row, pcs: 10 }], customers: [{ ...row, pcs: 10 }], quality, sku: [],
    trend: [{ mm: '08', net: 100, net_ly: 90, pcs: 10, pcs_ly: 8, cum_net: 100, cum_net_ly: 90 }],
    options: { brand: ['A'], cat: ['رنگ مو'], country: ['Iraq'], customer: [{ code: '1', label: 'customer', country: 'Iraq' }], product: [{ code: 'p', name: 'product', cat: 'رنگ مو' }] },
  } }
  const renderPreview = (section) => renderToStaticMarkup(React.createElement(router.MemoryRouter,
    { initialEntries: [`/rahkaran/export/preview?section=${section}`] }, React.createElement(Preview)))
  for (const section of ['overview','countries','customers','products','quality','comparison']) {
    const html = renderPreview(section)
    assert.match(html, /فروش صادراتی/)
    assert.match(html, /date-range/)
  }
  const countryTable = renderPreview('countries')
  const productsTable = renderPreview('products')
  assert.match(productsTable, /جستجوی نام یا کد مشتری/)
  assert.match(productsTable, /مشتری \/ گروه کالا \/ کالا/)
  assert.doesNotMatch(productsTable, /<summary>گزارش تفصیلی مشتری/)
  assert.match(countryTable, /جدول عملکرد کشورها/)
  assert.equal((countryTable.match(/tree:/g) || []).length, 1)
  const customerTable = renderPreview('countries&table=customers&country=Iraq')
  assert.match(customerTable, /جدول عملکرد کشورها و مشتریان/)
  assert.match(customerTable, /همه کشورها/)
  assert.equal((customerTable.match(/tree:/g) || []).length, 1)
  assert.match(renderPreview('customers&table=countries'), /جدول عملکرد کشورها/)
  const data = response.data
  response = { loading: true, data: null, error: null }
  assert.match(renderPreview('overview'), /loading/)
  response = { loading: false, data: null, error: 'SQL unavailable' }
  assert.match(renderPreview('overview'), /SQL unavailable/)
  response = { loading: false, error: null, data: { ...data, countries: [], customers: [], categories: [], brands: [], trend: [], goods: { nodes: [], total: {} }, quality: { kpis: {}, countries: [], customers: [], brands: [], categories: [] } } }
  for (const section of ['overview','countries','customers','products','quality','comparison']) assert.ok(renderPreview(section))
})

test('country tree nests customers under the right country and totals count each country once', () => {
  const { countryCustomerTree } = load('pages/ExportPreview.jsx')
  const { nodes, total } = countryCustomerTree(
    [{ key: 'Iraq', label: 'Iraq', net: 60, net_ly: 30, pcs: 6 }, { key: 'Oman', label: 'Oman', net: 40, net_ly: 20, pcs: 4 }],
    [{ key: 'a', label: 'A', country: 'Iraq', net: 60 }, { key: 'b', label: 'B', country: 'Oman', net: 40 }, { key: 'c', label: 'Inactive', country: 'Georgia', net: 0 }],
  )
  assert.equal(total.net, 100)
  assert.equal(total.net_ly, 50)
  assert.equal(total.growth, 1)
  assert.equal(nodes.filter((n) => n.level === 0).length, 3)
  for (const customer of nodes.filter((n) => n.level === 1)) {
    assert.equal(nodes.find((n) => n.id === customer.parent).key, customer.country)
    assert.equal(customer.code, customer.key)
  }
})
