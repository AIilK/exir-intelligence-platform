// پنل مغایرت‌گیری بانک (frontend/app/reconciliation) داخل داشبورد یکپارچه؛ دسترسی: ماژول «reconciliation».
// درخواست‌ها به /__reconciliation_proxy می‌روند و Proxy همین فرانت (vite.config.js) کلید API را اضافه می‌کند.
import ReconciliationClient from '@finance/reconciliation/reconciliation-client.tsx'
import '@finance/reconciliation/reconciliation.css'
import { useAuth } from '@finance/auth/auth.tsx'

export default function Reconciliation() {
  const look = useAuth().profile.user.preferences || {}
  return (
    <div className="fin-scope fin-embedded" data-view="reconciliation" data-theme={look.theme || 'teal'} data-wallpaper={look.wallpaper || 'none'}>
      <ReconciliationClient />
    </div>
  )
}
