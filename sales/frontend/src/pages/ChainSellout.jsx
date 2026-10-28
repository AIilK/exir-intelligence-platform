import { useState } from 'react'
import { useFetch, useApp, fmtInt, fmtPct, fmtCompact, faDigits } from '../lib.jsx'
import { Card, Kpi, Loading, ErrorBox, DataTable, Tabs, Empty } from '../components/ui.jsx'
import { Chart, CompareBars, HBar, baseOption } from '../components/Chart.jsx'
import { brandColor } from '../brands.js'
import { C } from '../cols.js'

const MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']
const monthName = (m) => (m ? `${MONTHS[Number(m.slice(5, 7)) - 1]} ${faDigits(m.slice(0, 4))}` : '—')
const compact = (v) => (v == null ? '—' : `${fmtCompact(v).value} ${fmtCompact(v).unit}`)

// دو مفهوم اصلی با زبان ساده:
//   فروش فروشگاه به مشتری = آنچه فروشگاه زنجیره‌ای به مصرف‌کننده فروخته (از فایل اکسل زنجیره)
//   فروش ما به فروشگاه   = آنچه ما به همان زنجیره فروخته‌ایم (فاکتور منهای برگشتی در کارآمد)
const OUT = 'فروش فروشگاه به مشتری'
const IN = 'فروش ما به فروشگاه'
const SO = {
  value: { key: 'value', label: `${OUT} (مبلغ)`, type: 'money', hint: 'مبلغ فروش فروشگاه به مصرف‌کننده طبق فایل زنجیره، با قیمت فروشگاه (پس از برگشتی، بدون ارزش افزوده، قبل از تخفیف سهم تأمین‌کننده)' },
  qty: { key: 'qty', label: `${OUT} (تعداد)`, type: 'int' },
  disc: { key: 'disc', label: 'تخفیف', type: 'money', hint: 'تخفیف گزارش‌شده در فایل زنجیره (هایپر می: سهم تأمین‌کننده؛ مادر دزفول: مبلغ تخفیف)' },
  sellin_net: { key: 'sellin_net', label: `${IN} (مبلغ)`, type: 'money', hint: 'فاکتورهای فروش ما به این زنجیره در همان ماه منهای برگشتی‌ها، با قیمت فروش ما (کارآمد، بدون ارزش افزوده)' },
  sellin_qty: { key: 'sellin_qty', label: `${IN} (تعداد)`, type: 'int' },
  st: { key: 'sell_through', label: 'فروش فروشگاه ÷ خرید از ما', type: 'pct', hint: 'تعداد فروش فروشگاه به مشتری ÷ تعداد فروش ما به فروشگاه در همان ماه. بیش از ۱۰۰٪: فروشگاه بیشتر از خریدش فروخته (از موجودی قبلی)؛ کمتر از ۱۰۰٪: بخشی از خرید هنوز در قفسه/انبار فروشگاه مانده' },
  avg: { key: 'avg_price', label: 'قیمت میانگین در فروشگاه', type: 'money', hint: 'مبلغ فروش فروشگاه ÷ تعداد' },
  sku: { key: 'sku', label: 'تنوع کالا', type: 'int' },
}

// کارت‌های هر زنجیره = ستون‌های اکسل خود زنجیره، با توضیح هر ستون. زنجیره‌ای که اینجا نیست کارت‌های عمومی را می‌گیرد.
// rel: رابطه با ستون‌های دیگر برای زیرنویس کارت (قابل تطبیق با فایل)
const FILE_CARDS = {
  // گزارش خانومی: فروش هر کالا با قیمت پایه (قیمت مصرف‌کننده) و قیمت فروش (پس از تخفیف سایت)
  'خانومی': {
    'مجموع تعداد فروش': { type: 'int', hint: 'تعداد کالاهای ما که خانومی به مشتری فروخته. برگشتی در فایل گزارش نشده.' },
    'مجموع مبلغ فروش (ریال)': { hint: 'مبلغ فروش به مشتری با قیمت فروش سایت (پس از تخفیف). همین عدد در بقیه بخش‌ها «فروش فروشگاه به مشتری» است.', rel: { pctOf: 'مجموع مبلغ پایه (ریال)' } },
    'مجموع مبلغ پایه (ریال)': { hint: 'همان فروش با قیمت پایه (قیمت مصرف‌کننده، قبل از تخفیف سایت). فاصله آن با مبلغ فروش، تخفیف سایت است.' },
  },
  // «گزارش خلاصه عملکرد فروش کالا» مادر دزفول (فقط رنگ موی پادینا ۱۰۰ میل)؛ زنجیره به‌جای بارکد، کد کالای خودش را داده
  'مادر دزفول': {
    'فروش (تعداد)': { type: 'int', hint: 'تعداد فروخته‌شده به مشتری، قبل از کسر برگشتی.' },
    'مرجوع (تعداد)': { type: 'int', hint: 'تعداد کالایی که مشتری‌ها پس داده‌اند.', rel: { pctOf: 'فروش (تعداد)' } },
    'فروش خالص (تعداد)': { type: 'int', hint: 'فروش منهای مرجوعی. همین عدد «تعداد فروش فروشگاه به مشتری» مادر دزفول است.', rel: { diffOf: ['فروش (تعداد)', 'مرجوع (تعداد)'] } },
    'فروش (مبلغ)': { hint: 'مبلغ فروش به مشتری قبل از کسر مرجوعی و تخفیف، بدون مالیات.' },
    'مرجوع (مبلغ)': { hint: 'مبلغ کالاهای پس‌داده‌شده.', rel: { pctOf: 'فروش (مبلغ)' } },
    'فروش خالص (مبلغ)': { hint: 'فروش منهای مرجوعی، قبل از تخفیف. همین عدد در بقیه بخش‌ها «فروش فروشگاه به مشتری» مادر دزفول حساب می‌شود.', rel: { diffOf: ['فروش (مبلغ)', 'مرجوع (مبلغ)'] } },
    'مبلغ تخفیف': { hint: 'تخفیفی که روی این فروش داده شده. در شهریور: آرایشی ۶۰٪ و بهداشتی ۴۰٪ فروش خالص؛ نرخ بالایی است و بهتر است با مادر دزفول چک شود که تخفیف به مشتری است یا سهم فروشگاه.', rel: { pctOf: 'فروش خالص (مبلغ)' } },
    'مانده': { hint: 'فروش خالص منهای تخفیف؛ یعنی مبلغی که پس از تخفیف می‌ماند (در فایل بهداشتی با نام «فروش خالص»).', rel: { diffOf: ['فروش خالص (مبلغ)', 'مبلغ تخفیف'] } },
    'مبلغ مالیات بر ارزش افزوده': { hint: 'مالیات گزارش‌شده در فایل‌ها. در فایل بهداشتی دقیقاً ۱۰٪ «مانده» است ولی در فایل آرایشی ۱۵٪؛ مبنای محاسبه آرایشی را باید از مادر دزفول پرسید.', rel: { pctOf: ['مانده', 'فروش خالص (مبلغ)'] } },
  },
}
// ستون‌های فایل زنجیره‌ها هم‌معنا ولی با نام‌های متفاوت‌اند؛ برای همه یک مجموعه کارت یکسان ساخته می‌شود.
// value/qty/tax/total: نام ستون در فایل آن زنجیره (total: null = در فایل نیست و از ارزش فروش + مالیات حساب می‌شود)
// tax: null + taxRate = مالیات در فایل نیست و با این نرخ برآورد می‌شود
// ret: برگشتی؛ neg = از ردیف‌های منفی فایل، نام ستون‌های برگشت، یا null = در فایل گزارش نشده
const STD_CHAINS = {
  'شهروند': { value: 'ارزش فروش', qty: 'تعداد', tax: 'مالیات فروش', total: 'جمع فروش',
    ret: { neg: true }, retNote: 'از ردیف‌های منفی فایل (برگشت از فروش) جمع شده و در ارزش فروش و تعداد کم شده است' },
  'نجم خاورمیانه': { value: 'فروش خالص ریالی', qty: 'فروش خالص تعدادی', tax: 'مالیات', total: null,
    ret: { value: 'ریالی برگشت از فروش', qty: 'تعدادی برگشت از فروش' },
    retNote: 'نجم برگشتی را در ستون‌های «ریالی/تعدادی برگشت از فروش» جدا گزارش می‌کند و «فروش خالص» پس از کسر آن است' },
  'مادر دزفول': { value: 'فروش خالص (مبلغ)', qty: 'فروش خالص (تعداد)', tax: 'مبلغ مالیات بر ارزش افزوده', total: null,
    ret: { value: 'مرجوع (مبلغ)', qty: 'مرجوع (تعداد)' },
    retNote: 'مادر دزفول مرجوعی را در ستون‌های «مرجوع (مبلغ/تعداد)» جدا گزارش می‌کند و «فروش خالص» = فروش − مرجوع است',
    disc: 'مبلغ تخفیف', discLabel: 'تخفیف', after: 'مانده',
    taxNote: 'مالیات فایل بهداشتی ۱۰٪ «مانده» (فروش خالص − تخفیف) است ولی فایل آرایشی ۱۵٪؛ مبنای آرایشی را باید از مادر دزفول پرسید.' },
  // گزارش هایپر می فقط مقدار و مبلغ فروش رفته و تخفیف سهم تأمین‌کننده را دارد (به تفکیک شعبه)؛ مالیات و برگشتی ندارد
  // مالیات و برگشتی در فایل نیست، پس کارت مالیات، جمع کل (که به مالیات وابسته است) و جمع برگشتی نمی‌آید (تصمیم کاربر)
  'هایپر می': { value: 'مبلغ فروش رفته', qty: 'مقدار فروش رفته', tax: null, total: null, ret: null, hideMissing: true,
    retNote: 'هایپر می برگشتی را جدا گزارش نمی‌کند و در فایلش ردیف منفی هم نیست',
    netNote: 'هایپر می برگشتی را جدا گزارش نمی‌کند',
    disc: 'مبلغ تخفیف سهم تامین کننده', discLabel: 'تخفیف سهم تأمین‌کننده',
    discNote: 'سهمی از تخفیف فروشگاه که به حساب ما (تأمین‌کننده) نوشته می‌شود؛ اگر خود فروشگاه هم سهمی داده باشد، در فایل نیامده.' },
}

/** کارت‌های یکسان زنجیره‌ها: ارزش فروش، فروش خالص تعدادی، مالیات، جمع کل، جمع برگشتی (+ تخفیف اگر فایل دارد) */
function StdCards({ data, chain, m }) {
  const col = Object.fromEntries(data.file_columns.map((c) => [c.label, c]))
  const v = (name) => col[name]?.total ?? 0
  const value = v(m.value)
  const estTax = !m.tax && m.taxRate
  const tax = m.tax ? v(m.tax) : estTax ? value * m.taxRate : null
  const total = m.total ? v(m.total) : tax == null ? null : value + tax
  const retValue = !m.ret ? null : m.ret.neg ? -(col[m.value]?.returns || 0) : v(m.ret.value)
  const retQty = !m.ret ? null : m.ret.neg ? -(col[m.qty]?.returns || 0) : v(m.ret.qty)
  const src = (name) => `ستون «${name}» در فایل ${chain}.`
  const afterRet = m.ret ? 'پس از کسر برگشتی' : 'برگشتی گزارش نشده'
  return (
    <>
      <Kpi label="ارزش فروش" value={value} sub={`بدون مالیات، ${afterRet}`}
        hint={`مبلغ فروش کالاهای ما به مشتری در فروشگاه‌های ${chain}، بدون مالیات${m.ret ? ' و پس از کسر برگشتی' : ''}. همین عدد در بقیه بخش‌ها «فروش فروشگاه به مشتری» است. ${src(m.value)}${m.netNote ? ` ${m.netNote}.` : ''}`} />
      <Kpi label="فروش خالص تعدادی" value={v(m.qty)} type="int" sub={`${afterRet} · ${fmtInt(data.kpis.sku)} کالا`}
        hint={`تعداد کالاهای ما که به مشتری فروخته شده${m.ret ? '، پس از کسر برگشتی' : ''}. ${src(m.qty)}${m.netNote ? ` ${m.netNote}.` : ''}`} />
      {!(m.hideMissing && tax == null) && <Kpi label="مالیات" value={tax} sub={estTax ? `برآورد ${fmtPct(m.taxRate, 0)} ارزش فروش؛ در فایل نیست` : `${fmtPct(value ? tax / value : null)} ارزش فروش`}
        hint={estTax
          ? `فایل ${chain} ستون مالیات ندارد؛ این عدد برآورد با نرخ ${fmtPct(m.taxRate, 0)} است، مثل شهروند و نجم (قیمت‌های فایل بدون مالیات‌اند).`
          : `مالیات بر ارزش افزوده‌ای که فروشگاه روی این فروش از مشتری گرفته. ${src(m.tax)}${m.taxNote ? ` ${m.taxNote}` : ''}`} />}
      {!(m.hideMissing && total == null) && <Kpi label="جمع کل" value={total} sub={estTax ? '= ارزش فروش + مالیات برآوردی' : '= ارزش فروش + مالیات'}
        hint={`مبلغی که مشتری‌ها پرداخته‌اند (با مالیات). ${m.total ? src(m.total) : `در فایل ${chain} ستون جدا ندارد و از جمع ارزش فروش و مالیات${estTax ? ' برآوردی' : ''} حساب شده.`}`} />}
      {!(m.hideMissing && !m.ret) && <Kpi label="جمع برگشتی" value={retValue}
        sub={m.ret ? `${fmtInt(retQty)} عدد · ${fmtPct(value ? retValue / value : null)} ارزش فروش` : 'در فایل گزارش نشده'}
        hint={`کالایی که مشتری‌ها به فروشگاه پس داده‌اند (بدون مالیات). ${m.retNote}.`} />}
      {m.disc && (
        <Kpi label={m.discLabel || 'تخفیف'} value={v(m.disc)}
          sub={`${fmtPct(value ? v(m.disc) / value : null)} ارزش فروش${m.after ? ` · مانده پس از تخفیف ${compact(v(m.after))}` : ''}`}
          hint={`تخفیفی که ${chain} روی این فروش گزارش کرده؛ از ارزش فروش و جمع کل کم نشده است.${m.after ? ` «${m.after}» در فایل = ارزش فروش − تخفیف.` : ''}${m.discNote ? ` ${m.discNote}` : ''} ${src(m.disc)}`} />
      )}
    </>
  )
}

const faNum = (v) => new Intl.NumberFormat('fa-IR', { maximumFractionDigits: 0 }).format(v)

/** یک کارت برای هر ستون عددی فایل زنجیره، با رابطه‌اش با ستون‌های دیگر */
function FileCards({ data, defs }) {
  const cols = data.file_columns
  const tot = Object.fromEntries(cols.map((c) => [c.label, c.total]))
  return cols.filter((c) => defs[c.label]).map((c) => {
    const d = defs[c.label]
    const isInt = d.type === 'int'
    const parts = []
    for (const p of [].concat(d.rel?.pctOf || [])) {
      if (tot[p]) parts.push(`${fmtPct(c.total / tot[p])} از ${p}`)
    }
    if (d.rel?.diffOf) {
      const [a, b] = d.rel.diffOf
      const s = (tot[a] || 0) - (tot[b] || 0)
      parts.push(Math.abs(s - c.total) < 1 ? `= ${a} − ${b} ✓` : `اختلاف با ${a} − ${b}: ${faNum(c.total - s)}`)
    }
    if (d.rel?.sumOf) {
      const s = d.rel.sumOf.reduce((a, k) => a + (tot[k] || 0), 0)
      parts.push(Math.abs(s - c.total) < 1 ? `= ${d.rel.sumOf.join(' + ')} ✓` : `اختلاف با ${d.rel.sumOf.join(' + ')}: ${faNum(c.total - s)} ریال`)
    }
    return <Kpi key={c.label} label={c.label} value={c.total} type={isInt ? 'int' : 'money'} hint={d.hint} sub={parts.join(' · ') || undefined} />
  })
}

const METRIC_TABS =[{ value: 'value', label: 'مبلغ' }, { value: 'qty', label: 'تعداد' }]

// زنجیره‌ای‌ها و فروشگاه‌های اینترنتی (خانومی، اسنپ) با همین صفحه؛ فقط منبع داده و واژه‌ها فرق دارد
const KINDS = {
  chain: { api: '/api/chain_sellout', one: 'زنجیره', many: 'زنجیره‌ها', where: 'فروشگاه‌های زنجیره‌ای', code: 'بارکد',
    match: 'گروه کالا از کارآمد با تطبیق بارکد', store: 'sd.chainOpen', prefix: 'chain' },
  online: { api: '/api/online_sellout', one: 'فروشگاه', many: 'فروشگاه‌ها', where: 'فروشگاه‌های اینترنتی', code: 'کد کالای فروشگاه',
    match: 'فروشگاه بارکد نمی‌دهد؛ کالا با فایل sku_map.csv در پوشه به کد کارآمد وصل می‌شود', store: 'sd.onlineOpen', prefix: 'online' },
}

/** فروش فروشگاه‌های زنجیره‌ای به مشتری (از فایل‌های ماهانه زنجیره‌ها)، در کنار فروش ما به همان فروشگاه‌ها */
export function ChainSelloutSection({ kind = 'chain' }) {
  const K = KINDS[kind]
  const [month, setMonth] = useState('')
  const [chain, setChain] = useState('')
  const q = new URLSearchParams({ ...(month && { month }), ...(chain && { chain }) }).toString()
  const { data, loading, error } = useFetch(`${K.api}${q ? `?${q}` : ''}`)
  const { unit } = useApp()
  const [dim, setDim] = useState('brands')
  const [metric, setMetric] = useState('value')
  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} />
  if (!data.month) {
    return (
      <Card title={`${OUT} در ${K.where}`}>
        <Empty text={`هنوز فایلی خوانده نشده است. فایل‌های اکسل ماهانه ${K.many} را در پوشه ${data.folder} بگذارید.`} />
        <FilesTable files={data.files} K={K} />
      </Card>
    )
  }
  const k = data.kpis
  const all = data.month === 'all'
  const period = all ? `همه ماه‌ها (${data.months.map(monthName).join('، ')})` : monthName(data.month)
  const multi = data.months.length > 1
  const chains = data.chains
  // شعب فروشگاه فقط برای زنجیره‌ای که فروش هر شعبه را می‌دهد (فعلاً فقط هایپر می) و فقط وقتی همان زنجیره انتخاب شده
  const hasStores = !!chain && data.stores.length > 0
  const stdMap = chain && data.file_columns?.length ? STD_CHAINS[chain] : null
  const fileDefs = chain && data.file_columns?.length ? (stdMap || FILE_CARDS[chain]) : null
  const fileNames = data.files.filter((f) => f.ok && f.chain === chain && (all || f.month === data.month)).map((f) => f.file)
  const prodCols = [C.label('کالا'), C.text('brand', 'برند'), C.text('category', 'گروه کالا'), C.text('barcode', K.code),
    SO.qty, SO.value, SO.sellin_qty, SO.st, SO.sellin_net,
    ...(!chain ? chains.map((c) => ({ key: `q:${c}`, label: `تعداد ${c}`, type: 'int' })) : []),
    ...(hasStores ? [{ key: 'stores', label: 'تعداد شعب با فروش', type: 'int' }] : [])]
  const prodRows = data.products.map((r) => {
    const o = { ...r }
    for (const c of chains) o[`q:${c}`] = r.by_chain?.[c] ?? null
    return o
  })
  const chainCols = [C.label(K.one), SO.value, C.share, SO.qty, SO.sellin_net, SO.sellin_qty, SO.st, SO.sku, SO.disc]
  const dimRows = data[dim]
  const dimLabel = { brands: 'برند', categories: 'گروه کالا' }[dim]
  const dimCols = [C.label(dimLabel), SO.qty, SO.value, C.share, SO.sellin_qty, SO.sellin_net, SO.st]
  return (
    <>
      <div className="chain-bar">
        <label className="inline-field"><span>ماه</span>
          <select value={data.month} onChange={(e) => setMonth(e.target.value)}>
            {[...data.months].reverse().map((m) => <option key={m} value={m}>{monthName(m)}</option>)}
            {multi && <option value="all">همه ماه‌ها</option>}
          </select>
        </label>
        <Tabs value={chain} onChange={setChain}
          tabs={[{ value: '', label: `همه ${K.many}` }, ...chains.map((c) => ({ value: c, label: c }))]} />
      </div>
      {fileDefs && (
        <div className="info muted small" style={{ marginBottom: 8 }}>
          کارت‌های زیر جمع ستون‌های فایل اکسل {chain} است ({period}، {fileNames.join('، ') || 'فایل بایگانی‌شده'}): {fmtInt(data.file_stats?.lines)} ردیف
          {data.file_stats?.return_lines ? `، که ${fmtInt(data.file_stats.return_lines)} ردیفش برگشت از فروش (منفی) است` : ''}؛ {fmtInt(k.sku)} کالا.
          روی علامت ؟ هر کارت بروید تا توضیحش را ببینید.
        </div>
      )}
      <div className="kpis">
        {stdMap ? <StdCards data={data} chain={chain} m={stdMap} /> : fileDefs ? <FileCards data={data} defs={fileDefs} /> : (
          <>
            <Kpi label={OUT} value={k.value} hint={SO.value.hint}
              sub={`${period} · ${chain || `${fmtInt(k.chains)} ${K.one}`}`} />
            <Kpi label={`${OUT} (تعداد)`} value={k.qty} type="int" sub={`${fmtInt(k.sku)} کالا`} />
          </>
        )}
        {hasStores && <Kpi label="شعب فروشگاه با فروش" value={k.stores} type="int" sub={`شعب ${chain}`} />}
      </div>
      {data.missing?.length > 0 && (
        <div className="info muted small" style={{ marginBottom: 12 }}>
          {K.many}یی که این ماه از ما خرید داشته‌اند ولی فایل فروش فروشگاه نفرستاده‌اند:{' '}
          {data.missing.map((m) => `${m.chain} (خرید از ما ${compact(m.sellin_net)})`).join('، ')}
        </div>
      )}
      <div className="grid g2">
        {!chain && (
          <Card title={`${OUT} در برابر ${IN}، به تفکیک ${K.one}`} className="span2"
            subtitle={`فروش فروشگاه با قیمت فروشگاه است و فروش ما با قیمت فروش ما؛ برای مقایسه حجم، ستون «فروش فروشگاه ÷ خرید از ما» (تعدادی) را ببینید. روی هر ${K.one} کلیک کنید`}>
            <CompareBars rows={data.by_chain} unit={unit} onClick={(r) => setChain(r.key)}
              series={[{ key: 'value', name: OUT, color: 0 }, { key: 'sellin_net', name: IN, color: 1 }]} />
          </Card>
        )}
        {hasStores && <StoreAnalysis data={data} chain={chain} unit={unit} />}
        <Card title="روند ماهانه" className="span2"
          subtitle={multi ? `${OUT} (میله) و ${IN} (خط) در هر ماه` : 'با اضافه شدن فایل ماه‌های بعد، روند ماهانه اینجا نمایش داده می‌شود'}>
          <MonthlyTrend rows={data.trend} unit={unit} />
        </Card>
        <Card title={`${OUT} به تفکیک ${dimLabel}`} className="span2"
          actions={<div className="head-actions">
            <Tabs value={metric} onChange={setMetric} tabs={METRIC_TABS} />
            <Tabs value={dim} onChange={setDim} tabs={[{ value: 'brands', label: 'برند' }, { value: 'categories', label: 'گروه کالا' }]} />
          </div>}
          subtitle={`نمودار بر اساس ${metric === 'qty' ? 'تعداد' : 'مبلغ'}؛ ${K.match}، کالای بدون تطبیق جدا آمده است`}>
          <div className="grid g2 inner">
            <HBar rows={[...dimRows].filter((r) => r[metric] > 0).sort((a, b) => b[metric] - a[metric]).slice(0, 15)}
              value={metric} valueType={metric === 'qty' ? 'int' : 'money'} unit={unit}
              colorOf={dim === 'brands' ? (r, t) => brandColor(r.label, t) : undefined} />
            <DataTable rows={dimRows} columns={dimCols} unit={unit} pageSize={10} dense exportName={`${K.prefix}-${dim}`} />
          </div>
        </Card>
        {!chain && (
          <Card title={`جدول ${K.many}`} className="span2">
            <DataTable rows={data.by_chain} columns={chainCols} unit={unit} search={false} exportName={`${K.prefix}-summary`}
              onRowClick={(r) => setChain(r.key)} />
          </Card>
        )}
        <Card title={`کالاها: ${OUT} و ${IN}`} className="span2"
          subtitle={`کالاهایی که ${K.one} از ما خریده ولی در فایل فروش فروشگاه نیامده‌اند، با فروش فروشگاه صفر آمده‌اند`}>
          <DataTable rows={prodRows} columns={prodCols} unit={unit} pageSize={15} dense exportName={`${K.prefix}-products-${data.month}`} />
        </Card>
        <Card title="فایل‌های دریافتی" className="span2"
          subtitle={`پوشه: ${data.folder} — هر ماه فایل‌های جدید را در همین پوشه بگذارید؛ داده هر ماه در بایگانی ذخیره می‌شود و با حذف یا جایگزینی فایل‌ها از بین نمی‌رود`}>
          <FilesTable files={data.files} K={K} />
        </Card>
      </div>
    </>
  )
}

/** تحلیل شعبه‌ای زنجیره‌هایی که فروش هر شعبه را می‌دهند (هایپر می) */
function StoreAnalysis({ data, chain, unit }) {
  const [metric, setMetric] = useState('value')
  const [sel, setSel] = useState(null)
  const stores = data.stores
  const brands = data.brands.filter((b) => stores.some((s) => s.brand_qty?.[b.label])).map((b) => b.label)
  const rows = stores.map((s) => {
    const o = { ...s }
    for (const b of brands) o[`b:${b}`] = s.brand_qty?.[b] ?? null
    return o
  })
  const total = stores.reduce((a, s) => a + (s.value || 0), 0)
  const top5 = [...stores].sort((a, b) => b.value - a.value).slice(0, 5).reduce((a, s) => a + s.value, 0)
  const avg = stores.length ? total / stores.length : 0
  const cols = [C.label('شعبه'), SO.value, C.share, SO.qty, SO.sku, SO.avg,
    ...brands.map((b) => ({ key: `b:${b}`, label: `تعداد ${b}`, type: 'int' }))]
  const selRow = stores.find((s) => s.key === sel)
  const prods = selRow ? data.store_products.filter((p) => p.store === selRow.label) : []
  const prodCols = [C.label('کالا'), C.text('brand', 'برند'), C.text('category', 'گروه کالا'), SO.qty, SO.value]
  return (
    <>
      <Card title={`فروش شعب ${chain} به مشتری`} className="span2"
        subtitle={`${fmtInt(stores.length)} شعبه با فروش · میانگین هر شعبه ${compact(avg)} · ۵ شعبه اول ${fmtPct(total ? top5 / total : null)} از فروش · روی هر شعبه کلیک کنید تا کالاهایش را ببینید`}
        actions={<Tabs value={metric} onChange={setMetric} tabs={METRIC_TABS} />}>
        <div className="grid g2 inner">
          <HBar rows={[...stores].sort((a, b) => b[metric] - a[metric])} value={metric}
            valueType={metric === 'qty' ? 'int' : 'money'} unit={unit} onClick={(r) => setSel(r.key)} />
          <DataTable rows={rows} columns={cols} unit={unit} pageSize={12} dense exportName={`stores-${chain}`}
            onRowClick={(r) => setSel(r.key)} />
        </div>
      </Card>
      {selRow && (
        <Card title={`کالاهای ${selRow.label.startsWith('شعبه') ? '' : 'شعبه '}${selRow.label}`} className="span2"
          subtitle={`${compact(selRow.value)} · ${fmtInt(selRow.qty)} عدد · ${fmtInt(prods.length)} کالا`}
          actions={<button className="btn ghost" onClick={() => setSel(null)}>بستن</button>}>
          <div className="grid g2 inner">
            <BrandSplit store={selRow} unit={unit} />
            <DataTable rows={prods} columns={prodCols} unit={unit} pageSize={10} dense exportName={`store-${selRow.label}`} />
          </div>
        </Card>
      )}
    </>
  )
}

function BrandSplit({ store, unit }) {
  const rows = Object.entries(store.brand_value || {}).map(([b, v]) => ({ key: b, label: b, value: v, qty: store.brand_qty?.[b] }))
    .sort((a, b) => b.value - a.value)
  return <HBar rows={rows} value="value" unit={unit} colorOf={(r, t) => brandColor(r.label, t)} />
}

function FilesTable({ files, K }) {
  const cols = [C.text('file', 'فایل'), C.text('chain', K.one), { key: 'month', label: 'ماه', render: (r) => monthName(r.month), csv: (r) => r.month },
    C.text('month_from', 'تشخیص ماه از'), { key: 'rows', label: 'سطر', type: 'int' }, { key: 'qty', label: 'تعداد', type: 'int' },
    { key: 'status', label: 'وضعیت', render: (r) => (r.ok ? 'خوانده شد' : <span className="neg">{r.error}</span>), csv: (r) => (r.ok ? 'خوانده شد' : r.error) }]
  return <DataTable rows={files} columns={cols} unit="million" search={false} pageSize={20} dense />
}

function MonthlyTrend({ rows, unit }) {
  if (!rows.length) return <Empty />
  const months = [...new Set(rows.map((r) => r.month))].sort()
  const chains = [...new Set(rows.map((r) => r.chain))]
  const sum = (m, key) => rows.filter((r) => r.month === m).reduce((s, r) => s + (r[key] || 0), 0)
  return (
    <Chart height={280} option={(t) => ({
      grid: { left: 12, right: 12, top: 36, bottom: 8, containLabel: true },
      legend: { top: 0, right: 0, textStyle: { color: t.text } },
      tooltip: { ...baseOption(t).tooltip, trigger: 'axis',
        valueFormatter: (v) => `${compact(v)}` },
      xAxis: { type: 'category', inverse: true, data: months.map(monthName), axisLabel: { color: t.text },
        axisLine: { lineStyle: { color: t.axis } }, axisTick: { show: false } },
      yAxis: { type: 'value', position: 'right', splitLine: { lineStyle: { color: t.grid } },
        axisLabel: { color: t.text, formatter: (v) => fmtCompact(v).value } },
      series: [
        ...chains.map((c, i) => ({ name: c, type: 'bar', stack: 'so', barMaxWidth: 36, itemStyle: { color: t.series[i % t.series.length] },
          data: months.map((m) => rows.find((r) => r.month === m && r.chain === c)?.value ?? 0) })),
        { name: IN, type: 'line', symbolSize: 8, lineStyle: { width: 2, type: 'dashed' },
          itemStyle: { color: t.textStrong }, data: months.map((m) => sum(m, 'sellin_net')) },
      ],
    })} />
  )
}

/** فیلتر شعبه فقط شعبه(های) زنجیره‌ای است */
export const isChainOnly = (branches) => branches?.length > 0 && branches.every((b) => String(b).includes('زنجیره'))
/** فیلتر شعبه فقط شعبه «اینترنتی» است */
export const isOnlineOnly = (branches) => branches?.length > 0 && branches.every((b) => String(b).includes('اینترنت'))

/** بخش کشویی «فروش فروشگاه‌های زنجیره‌ای به مشتری»: صفحه مثل بقیه شعب می‌ماند و جزئیات زنجیره‌ها با کلیک باز می‌شود */
export function ChainSelloutBlock({ kind = 'chain' }) {
  const K = KINDS[kind]
  const [open, setOpen] = useState(() => {
    try { return localStorage.getItem(K.store) === '1' } catch { return false }
  })
  const toggle = () => {
    setOpen((o) => {
      try { localStorage.setItem(K.store, o ? '0' : '1') } catch { /* ignore */ }
      return !o
    })
  }
  return (
    <section className={`chain-sellout card${open ? ' open' : ''}`}>
      <button className="chain-toggle" onClick={toggle} aria-expanded={open}>
        <span className="chain-caret" aria-hidden>{open ? '▾' : '◂'}</span>
        <span>
          <b>جزئیات {K.where}: {OUT} و {IN}</b>
          <span className="muted small"> — از فایل‌های اکسل ماهانه {K.many}؛ {open ? 'برای بستن کلیک کنید' : 'برای باز کردن کلیک کنید'}</span>
        </span>
      </button>
      {open && (
        <div className="chain-body">
          <p className="muted small">فیلتر تاریخ و بقیه فیلترهای سراسری روی این بخش اثر ندارند؛ ماه و {K.one} را همین‌جا انتخاب کنید.</p>
          <ChainSelloutSection kind={kind} />
        </div>
      )}
    </section>
  )
}
