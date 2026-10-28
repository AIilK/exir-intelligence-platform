// الارم‌های ماژول‌های فروش بالای صفحه‌های داشبورد یکپارچه (جایگزین کارت‌های Agent).
// همان نوار الارم مالی (frontend/app/alarms)؛ فقط الارم ماژول‌هایی که کاربر به آن‌ها دسترسی دارد.
import { useNavigate } from 'react-router-dom'
import { AlarmStrip } from '@finance/alarms/alarms.tsx'

/** view مالی ← /finance/view؛ مسیر یکپارچه (با / شروع می‌شود) ← همان مسیر */
export function useAlarmGo() {
  const nav = useNavigate()
  return (v) => nav(v.startsWith('/') ? v : `/finance/${v}`)
}

export default function PageAlarms({ modules, title }) {
  const go = useAlarmGo()
  return (
    <div className="fin-scope fin-inline u-page-alarms">
      <AlarmStrip modules={modules} title={title} onGo={go} />
    </div>
  )
}
