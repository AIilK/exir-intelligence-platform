// Vite plugin: small load-time adjustments so the two original dashboards can be
// mounted inside the unified shell WITHOUT editing their source folders.
//  - finance: API calls go through this dev server's proxy instead of http://host:8000,
//    The root <Page> itself accepts a controlled `view` / `onViewChange` (the unified sidebar picks the page);
//    here we only check that signature is still there.
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

// one shared portal host; display: contents (unified.css) so the scope's page background never shows
const FIN_PORTAL_ROOT = `
function __finPortalRoot() {
  let el = document.getElementById("fin-portal-root");
  if (!el) {
    el = document.createElement("div");
    el.id = "fin-portal-root";
    el.className = "fin-scope fin-portal";
    document.body.appendChild(el);
  }
  return el;
}
`

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
        // drawers / peek panels / chatbot portal into document.body, outside .fin-scope where the
        // finance CSS lives; give them a .fin-scope container of their own instead
        if (out.includes(', document.body)') && /\bcreatePortal\b/.test(out)) {
          out = out.split(', document.body)').join(', __finPortalRoot())') + FIN_PORTAL_ROOT
        }
        if (file.endsWith('/dashboard-client.tsx')) {
          if (!/export default function Page\(props: \{ view\?: View; onViewChange\?:/.test(out)) {
            throw new Error(`[unified] finance Page no longer accepts { view, onViewChange } in ${id}`)
          }
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
