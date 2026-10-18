// Vite plugin: small load-time adjustments so the two original dashboards can be
// mounted inside the unified shell WITHOUT editing their source folders.
//  - finance: API calls go through this dev server's proxy instead of http://host:8000,
//    and the root <Page> accepts a controlled `view` (the unified sidebar picks the page).
//  - sales: charts always use the dark palette, tuned to the finance navy surfaces.
// Each replacement must match; otherwise the dev server fails loudly instead of
// silently rendering something half-wired after an upstream change.

const norm = (p) => p.replace(/\\/g, '/').toLowerCase()

function replaceOrThrow(code, file, from, to, { all = false } = {}) {
  const re = from instanceof RegExp ? from : null
  const hit = re ? re.test(code) : code.includes(from)
  if (!hit) throw new Error(`[unified] expected pattern not found in ${file}: ${String(from).slice(0, 80)}`)
  if (re) {
    re.lastIndex = 0
    return code.replace(re, to)
  }
  return all ? code.split(from).join(to) : code.replace(from, to)
}

const FIN_ABS_API = /`http:\/\/\$\{[^`}]*\}:8000\/api\/v1/g

const CONTROLLED_PAGE = `export default function Page(__props: { view?: View; onViewChange?: (v: View) => void } = {}) {
  const [__innerView, __setInnerView] = useState<View>(__props.view ?? "management");
  const view: View = __props.view ?? __innerView;
  const setView = (v: View) => { if (__props.onViewChange) __props.onViewChange(v); else __setInnerView(v); };
  const [__unusedView] = useState<View>("management"),`

export default function embedSources({ financeApp, salesSrc }) {
  const fin = norm(financeApp)
  const sales = norm(salesSrc)
  return {
    name: 'unified-embed-sources',
    enforce: 'pre',
    transform(code, id) {
      const file = norm(id.split('?')[0])
      if (file.startsWith(fin) && /\.(tsx?|jsx?)$/.test(file)) {
        let out = code
        if (FIN_ABS_API.test(out)) {
          FIN_ABS_API.lastIndex = 0
          out = out.replace(FIN_ABS_API, '`/api/v1')
        }
        if (file.endsWith('/dashboard-client.tsx')) {
          out = replaceOrThrow(out, id,
            /export default function Page\(\)\s*\{\s*const \[view, setView\] = useState<View>\("management"\),/,
            CONTROLLED_PAGE)
          // the manager report is shown on the unified manager page (not on the finance summary)
          if (!/\nfunction ManagerPanel\(/.test(out)) throw new Error(`[unified] ManagerPanel not found in ${id}`)
          out += '\nexport { ManagerPanel };\n'
        }
        return out === code ? null : { code: out, map: null }
      }
      if (file === `${sales}/components/chart.jsx`) {
        let out = code
        out = replaceOrThrow(out, id, 'useState(!!q?.matches)', 'useState(true)')
        out = replaceOrThrow(out, id, 'setDark(e.matches)', 'setDark(true)')
        // dark chart surfaces → finance navy family
        for (const [a, b] of [["'#1a1a19'", "'#0d1d2a'"], ["'#2e2e2c'", "'#1f3a4a'"], ["'#4a4a46'", "'#3a5767'"], ["'#c3c2b7'", "'#a9bec6'"]]) {
          out = replaceOrThrow(out, id, a, b, { all: true })
        }
        return { code: out, map: null }
      }
      return null
    },
  }
}
