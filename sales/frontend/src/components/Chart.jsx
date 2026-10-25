import { useEffect, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import { fmtInt, fmtMoney, fmtPct, UNITS, faDigits, fmtFull, fmtExact } from '../lib.jsx'

// پالت مرجع (اعتبارسنجی‌شده برای کم‌بینایی رنگ) — ترتیب ثابت، بدون چرخش
const SERIES = {
  light: ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948'],
  dark: ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'],
}
export const SEQ = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b']
// طیف نارنجی هم‌خانواده رنگ «درخواست» (رنگ دوم پالت)
export const SEQ_ORANGE = ['#fde0d3', '#f9bfa5', '#f49c75', '#eb6834', '#c9521f', '#9e3f17', '#72300f']

function useDark() {
  const q = window.matchMedia?.('(prefers-color-scheme: dark)')
  const [dark, setDark] = useState(!!q?.matches)
  useEffect(() => {
    if (!q) return
    const h = (e) => setDark(e.matches)
    q.addEventListener('change', h)
    return () => q.removeEventListener('change', h)
  }, [])
  return dark
}

export function useTheme() {
  const dark = useDark()
  return {
    dark,
    series: dark ? SERIES.dark : SERIES.light,
    text: dark ? '#c3c2b7' : '#52514e',
    textStrong: dark ? '#ffffff' : '#0b0b0b',
    grid: dark ? '#2e2e2c' : '#ecebe7',
    axis: dark ? '#4a4a46' : '#c9c8c2',
    surface: dark ? '#1a1a19' : '#ffffff',
  }
}

export function baseOption(t) {
  return {
    textStyle: { fontFamily: 'Vazirmatn, Tahoma, sans-serif', color: t.text },
    color: t.series,
    animationDuration: 300,
    tooltip: {
      backgroundColor: t.surface,
      borderColor: t.axis,
      textStyle: { color: t.textStrong, fontFamily: 'Vazirmatn, Tahoma, sans-serif' },
      extraCssText: 'direction: rtl; text-align: right; box-shadow: 0 2px 8px rgba(0,0,0,.12);',
    },
  }
}

export function Chart({ option, height = 320, onClick }) {
  const t = useTheme()
  const merged = { ...baseOption(t), ...option(t) }
  return (
    <ReactECharts
      option={merged}
      notMerge
      style={{ height, width: '100%' }}
      onEvents={onClick ? { click: (p) => onClick(p) } : undefined}
    />
  )
}

const axisLabel = (t, fmt) => ({ color: t.text, formatter: fmt })
const splitLine = (t) => ({ lineStyle: { color: t.grid } })

/** نمودار میله‌ای افقی رتبه‌ای (یک سری، رنگ ثابت). */
/** colorOf(row, t): رنگ جدا برای هر میله (مثلاً رنگ برند)؛ بدون آن همه میله‌ها رنگ colorIndex پالت‌اند */
export function HBar({ rows, value = 'net', unit, height, onClick, valueType = 'money', colorIndex = 0, colorOf, labelWidth = 150 }) {
  const data = [...rows].reverse()
  const fmt = (v) => (valueType === 'money' ? fmtMoney(v, unit) : valueType === 'pct' ? fmtPct(v) : fmtInt(v))
  const h = height || Math.max(180, data.length * 26 + 50)
  return (
    <Chart
      height={h}
      onClick={onClick && ((p) => onClick(data[p.dataIndex]))}
      option={(t) => ({
        grid: { left: 70, right: 12, top: 8, bottom: 24, containLabel: true },
        tooltip: {
          ...baseOption(t).tooltip,
          trigger: 'axis',
          axisPointer: { type: 'shadow' },
          formatter: (ps) => `${ps[0].name}<br/><b>${fmt(ps[0].value)}</b>${valueType === 'money' ? ' ' + UNITS[unit].label : ''}` +
            (valueType === 'money' ? `<br/><span style="opacity:.75">${fmtFull(ps[0].value)}</span>` : valueType === 'int' ? `<br/><span style="opacity:.75">${fmtExact(ps[0].value)}</span>` : ''),
        },
        xAxis: { type: 'value', inverse: true, axisLabel: axisLabel(t, (v) => fmt(v)), splitLine: splitLine(t) },
        yAxis: {
          type: 'category',
          position: 'right',
          data: data.map((r) => r.label),
          axisLabel: { color: t.text, width: labelWidth, overflow: 'truncate' },
          axisLine: { lineStyle: { color: t.axis } },
          axisTick: { show: false },
        },
        series: [{
          type: 'bar',
          data: colorOf ? data.map((r) => ({ value: r[value], itemStyle: { color: colorOf(r, t) } })) : data.map((r) => r[value]),
          barMaxWidth: 16,
          itemStyle: { color: t.series[colorIndex], borderRadius: [4, 0, 0, 4] },
          cursor: onClick ? 'pointer' : 'default',
          label: { show: data.length <= 12, position: 'left', color: t.text, formatter: (p) => fmt(p.value) },
        }],
      })}
    />
  )
}

/** روند روزانه: میله فروش خالص (+ برگشتی) و خط درخواست؛ محور زمان راست‌به‌چپ. */
export function TrendChart({ trend, unit, height = 300, showReq = true, fullLabel = false }) {
  const dates = trend.map((d) => faDigits(fullLabel ? d.date : d.date.slice(5)))
  const hasReq = showReq && trend.some((d) => d.req_net)
  return (
    <Chart
      height={height}
      option={(t) => ({
        grid: { left: 12, right: 12, top: 36, bottom: 8, containLabel: true },
        legend: { top: 0, right: 0, textStyle: { color: t.text }, itemGap: 16 },
        tooltip: {
          ...baseOption(t).tooltip,
          trigger: 'axis',
          formatter: (ps) =>
            `${faDigits(trend[ps[0].dataIndex].date)}<br/>` +
            ps.map((p) => `${p.marker} ${p.seriesName}: <b>${fmtMoney(p.value, unit)}</b> <span style="opacity:.75">(${fmtFull(p.value)})</span>`).join('<br/>') +
            `<br/><span style="opacity:.7">${UNITS[unit].label}</span>`,
        },
        xAxis: { type: 'category', data: dates, inverse: true, axisLabel: { color: t.text },
          axisLine: { lineStyle: { color: t.axis } }, axisTick: { show: false } },
        yAxis: { type: 'value', position: 'right', axisLabel: axisLabel(t, (v) => fmtMoney(v, unit)), splitLine: splitLine(t) },
        series: [
          { name: 'فروش خالص', type: 'bar', data: trend.map((d) => d.net), barMaxWidth: 22,
            itemStyle: { color: t.series[0], borderRadius: [4, 4, 0, 0] } },
          { name: 'برگشت از فروش', type: 'bar', data: trend.map((d) => -(d.returns_net || 0)), barMaxWidth: 22,
            barGap: '10%', itemStyle: { color: t.series[7], borderRadius: [0, 0, 4, 4] } },
          ...(hasReq ? [{ name: 'درخواست (سفارش)', type: 'line', data: trend.map((d) => d.req_net || 0),
            symbolSize: 8, lineStyle: { width: 2 }, itemStyle: { color: t.series[1], borderColor: t.surface, borderWidth: 2 } }] : []),
        ],
      })}
    />
  )
}

/** میله‌ای گروهی افقی برای مقایسه دو شاخص هم‌واحد. */
export function CompareBars({ rows, series, unit, onClick }) {
  const data = [...rows].reverse()
  return (
    <Chart
      height={Math.max(220, data.length * 34 + 60)}
      onClick={onClick && ((p) => onClick(data[p.dataIndex]))}
      option={(t) => ({
        grid: { left: 12, right: 12, top: 32, bottom: 20, containLabel: true },
        legend: { top: 0, right: 0, textStyle: { color: t.text } },
        tooltip: {
          ...baseOption(t).tooltip, trigger: 'axis', axisPointer: { type: 'shadow' },
          formatter: (ps) => `${ps[0].name}<br/>` + ps.map((p) => `${p.marker} ${p.seriesName}: <b>${fmtMoney(p.value, unit)}</b> <span style="opacity:.75">(${fmtFull(p.value)})</span>`).join('<br/>') +
            `<br/><span style="opacity:.7">${UNITS[unit].label}</span>`,
        },
        xAxis: { type: 'value', inverse: true, axisLabel: axisLabel(t, (v) => fmtMoney(v, unit)), splitLine: splitLine(t) },
        yAxis: { type: 'category', position: 'right', data: data.map((r) => r.label),
          axisLabel: { color: t.text, width: 150, overflow: 'truncate' },
          axisLine: { lineStyle: { color: t.axis } }, axisTick: { show: false } },
        series: series.map((s, i) => ({
          name: s.name, type: 'bar', data: data.map((r) => r[s.key] || 0), barMaxWidth: 12, barGap: '20%',
          cursor: onClick ? 'pointer' : 'default',
          itemStyle: { color: t.series[s.color ?? i], borderRadius: [4, 0, 0, 4] },
        })),
      })}
    />
  )
}

/** نقشه حرارتی (رنگ ترتیبی تک‌فام). */
export function Heatmap({ rows, xKey, yKey, vKey, unit, onClickY, palette = SEQ }) {
  const xs = [...new Set(rows.map((r) => r[xKey]))].sort()
  const ys = [...new Set(rows.map((r) => r[yKey]))]
  const tot = Object.fromEntries(ys.map((y) => [y, rows.filter((r) => r[yKey] === y).reduce((a, r) => a + r[vKey], 0)]))
  ys.sort((a, b) => tot[a] - tot[b])
  const data = rows.map((r) => [xs.indexOf(r[xKey]), ys.indexOf(r[yKey]), r[vKey]])
  const max = Math.max(1, ...rows.map((r) => r[vKey]))
  return (
    <Chart
      height={Math.max(260, ys.length * 24 + 80)}
      onClick={onClickY && ((p) => onClickY(ys[p.value[1]]))}
      option={(t) => ({
        grid: { left: 12, right: 12, top: 8, bottom: 56, containLabel: true },
        tooltip: { ...baseOption(t).tooltip, formatter: (p) =>
          `${ys[p.value[1]]} — ${faDigits(xs[p.value[0]])}<br/><b>${fmtMoney(p.value[2], unit)}</b> ${UNITS[unit].label}<br/><span style="opacity:.75">${fmtFull(p.value[2])}</span>` },
        xAxis: { type: 'category', inverse: true, data: xs.map((x) => faDigits(x.slice(5))), axisLabel: { color: t.text },
          splitArea: { show: false }, axisTick: { show: false } },
        yAxis: { type: 'category', position: 'right', data: ys, axisLabel: { color: t.text }, axisTick: { show: false } },
        visualMap: { min: 0, max, calculable: false, text: [fmtMoney(max, unit), '۰'], orient: 'horizontal', left: 'center', bottom: 0, itemHeight: 140,
          inRange: { color: t.dark ? [...palette].reverse() : palette }, textStyle: { color: t.text },
          formatter: (v) => fmtMoney(v, unit) },
        series: [{ type: 'heatmap', data: data.filter((d) => d[2] > 0), itemStyle: { borderColor: t.surface, borderWidth: 2, borderRadius: 3 },
          cursor: onClickY ? 'pointer' : 'default' }],
      })}
    />
  )
}

/** منحنی پارتو (سهم تجمعی). */
/**
 * منحنی پارتو (سهم تجمعی) با نواحی کلاس A / B / C، جمله خلاصه و کارت هر کلاس.
 * classes: [{abc, count, net, share}] از analytics.pareto
 */
export function ParetoChart({ curve, classes = [], height = 280, what = 'آیتم' }) {
  const t0 = useTheme()
  const cls = Object.fromEntries(classes.map((c) => [c.abc, c]))
  const n = classes.reduce((a, c) => a + c.count, 0)
  const nA = cls.A?.count || 0, nB = cls.B?.count || 0, nC = cls.C?.count || 0
  const xA = n ? nA / n : 0, xAB = n ? (nA + nB) / n : 0
  const colors = { A: t0.series[0], B: t0.series[1], C: t0.axis }
  const zone = (from, to, k, c) => [
    { xAxis: from, name: c ? `${k} · ${fmtInt(c.count)} ${what}` : k, itemStyle: { color: colors[k], opacity: 0.1 } },
    { xAxis: to },
  ]
  return (
    <div className="pareto">
      {n > 0 && (
        <div className="pareto-head">
          <b>{fmtPct(cls.A?.share, 0)} فروش</b> فقط از <b>{fmtInt(nA)} {what}</b> می‌آید
          <span className="muted"> — یعنی {fmtPct(xA, 0)} از {fmtInt(n)} {what} دارای فروش. </span>
          {nC > 0 && <span className="muted">در مقابل {fmtInt(nC)} {what} ({fmtPct(nC / n, 0)}) روی هم فقط {fmtPct(cls.C?.share, 0)} فروش را دارند.</span>}
        </div>
      )}
      <Chart
        height={height}
        option={(t) => ({
          grid: { left: 12, right: 12, top: 28, bottom: 30, containLabel: true },
          tooltip: { ...baseOption(t).tooltip, trigger: 'axis',
            formatter: (ps) => {
              const [x, y] = ps[0].value
              return `${fmtInt(Math.max(1, Math.round(x * n)))} ${what} اول (${fmtPct(x, 0)} از ${what}‌ها)<br/>← <b>${fmtPct(y)}</b> از فروش خالص`
            } },
          xAxis: { type: 'value', inverse: true, min: 0, max: 1, axisLabel: axisLabel(t, (v) => fmtPct(v, 0)), splitLine: splitLine(t),
            name: `درصد ${what}‌ها (از پرفروش به کم‌فروش)`, nameLocation: 'middle', nameGap: 26, nameTextStyle: { color: t.text } },
          yAxis: { type: 'value', position: 'right', min: 0, max: 1, axisLabel: axisLabel(t, (v) => fmtPct(v, 0)), splitLine: splitLine(t) },
          series: [{
            type: 'line', data: curve.map((c) => [c.x, c.y]), showSymbol: false, lineStyle: { width: 2.5, color: t.series[0] },
            markArea: n ? { silent: true, label: { color: t.text, position: 'insideTop', fontSize: 11 },
              data: [zone(0, xA, 'A', cls.A), zone(xA, xAB, 'B', cls.B), zone(xAB, 1, 'C', cls.C)] } : undefined,
            markLine: { silent: true, symbol: 'none', lineStyle: { color: t.axis, type: 'dashed' },
              // خط‌چین ۸۰٪ / ۹۵٪ و مرز کلاس‌ها بدون برچسب (درصد روی محور و تعداد روی نواحی هست)
              label: { show: false },
              data: [{ yAxis: 0.8 }, { yAxis: 0.95 }, ...(n ? [{ xAxis: xA }, { xAxis: xAB }] : [])] },
          }],
        })}
      />
      {n > 0 && (
        <div className="abc-cards">
          {['A', 'B', 'C'].map((k) => cls[k] && (
            <div key={k} className="abc-card" style={{ borderColor: colors[k] }}>
              <div className="abc-k" style={{ color: k === 'C' ? undefined : colors[k] }}>کلاس {k}</div>
              <div><b>{fmtInt(cls[k].count)}</b> {what} <span className="muted">({fmtPct(cls[k].count / n, 0)} از {what}‌ها)</span></div>
              <div><b>{fmtPct(cls[k].share, 0)}</b> <span className="muted">از فروش</span></div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
