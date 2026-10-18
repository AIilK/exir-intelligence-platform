// PostCSS plugin: prefixes every selector of a source app's CSS with a scope class,
// so the finance and sales stylesheets (both written as whole-page globals) can live
// in one document without overriding each other. :root / html / body / :host become
// the scope element itself.

const ROOT = /^(:root|:host|html|body)(?![\w-])/
const ATTRS = /^((?:\[[^\]]*\]|:not\((?:[^()]|\([^)]*\))*\))*)/

export function scopeSelector(selector, scope) {
  let s = selector.trim()
  if (!s || s.startsWith(scope)) return s
  let suffix = ''
  let matched = false
  for (let m = s.match(ROOT); m; m = s.match(ROOT)) {
    matched = true
    s = s.slice(m[0].length)
    const a = s.match(ATTRS)[1]
    suffix += a
    s = s.slice(a.length).trim()
  }
  if (matched) return `${scope}${suffix}${s ? ` ${s}` : ''}`
  return `${scope} ${s}`
}

/** rules: [{ test: (normalizedFilePath) => boolean, scope: '.my-scope' }] */
export default function scopeCss({ rules }) {
  return {
    postcssPlugin: 'scope-css',
    Once(root, { result }) {
      const file = String(root.source?.input?.file || result.opts.from || '').replace(/\\/g, '/').split('?')[0]
      const rule = rules.find((r) => r.test(file))
      if (!rule) return
      root.walkRules((r) => {
        for (let p = r.parent; p; p = p.parent) {
          if (p.type === 'atrule' && /keyframes$/i.test(p.name)) return
        }
        r.selectors = r.selectors.map((sel) => scopeSelector(sel, rule.scope))
      })
    },
  }
}
scopeCss.postcss = true
