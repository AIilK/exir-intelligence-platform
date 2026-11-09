import React, { lazy, Suspense } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import 'vazirmatn/Vazirmatn-font-face.css'
// source apps' global styles — scoped to .sales-scope / .fin-scope at build time
import '@sales/styles.css'
import '@finance/globals.css'
import '@finance/agent.css'
import './unified.css'
import '@finance/auth/auth.css'
import AuthGate, { installAuthFetch } from '@finance/auth/auth.tsx'
import { AppProvider } from '@sales/lib.jsx'
import Shell from './Shell.jsx'
import SalesFrame from './SalesFrame.jsx'

// هر صفحه یک فایل جدا (chunk) است و فقط وقتی کاربر به آن صفحه می‌رود دانلود می‌شود؛
// پس صفحه اول به‌جای کل اپ فقط بخش مشترک (پوسته، ورود، هشدارها) را می‌گیرد.
const lazyCache = new Map()
const page = (load, name = 'default') => {
  const key = `${load}|${name}`
  if (!lazyCache.has(key)) lazyCache.set(key, lazy(() => load().then((m) => ({ default: m[name] }))))
  const C = lazyCache.get(key)
  return <Suspense fallback={<div className="u-page-loading">در حال بارگذاری…</div>}><C /></Suspense>
}
const ManagerOverview = () => import('./pages/ManagerOverview.jsx')
const HybridList = () => import('./pages/HybridList.jsx')
const HybridFile = () => import('./pages/HybridFile.jsx')
const VisitorFile = () => import('./pages/VisitorFile.jsx')
const RahkaranList = () => import('./pages/RahkaranList.jsx')
const RahkaranFile = () => import('./pages/RahkaranFile.jsx')
const FinanceView = () => import('./FinanceView.jsx')
const Reconciliation = () => import('./pages/Reconciliation.jsx')
const ExcelReports = () => import('./pages/ExcelReports.jsx')
const SalesOverview = () => import('@sales/pages/Overview.jsx')
const Hybrid = () => import('@sales/pages/Hybrid.jsx')
const Team = () => import('@sales/pages/Team.jsx')
const Products = () => import('@sales/pages/Products.jsx')
const Customers = () => import('@sales/pages/Customers.jsx')
const Analysis = () => import('@sales/pages/Analysis.jsx')
const Inventory = () => import('@sales/pages/Inventory.jsx')
const Detail = () => import('@sales/pages/Detail.jsx')
const DataSource = () => import('@sales/pages/DataSource.jsx')
const Rahkaran = () => import('@sales/pages/Rahkaran.jsx')
const RahkaranReports = () => import('@sales/pages/RahkaranReports.jsx')
const RahkaranCompare = () => import('@sales/pages/RahkaranCompare.jsx')
const Reorder = () => import('@sales/pages/Reorder.jsx')
const Export = () => import('@sales/pages/Export.jsx')
const RahkaranCommission = () => import('@sales/pages/RahkaranCommission.jsx')
const Commission = () => import('@sales/pages/Commission.jsx')
const Contest = () => import('@sales/pages/Contest.jsx')

// ورود و سطح دسترسی (بک‌اند مالی /api/v1/auth): بدون ورود هیچ صفحه‌ای باز نمی‌شود.
installAuthFetch()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <AuthGate screenClass="fin-scope">
    <AppProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Shell />}>
            <Route index element={page(ManagerOverview)} />
            <Route path="files/hybrids" element={page(HybridList)} />
            <Route path="files/hybrids/:name" element={page(HybridFile)} />
            <Route path="files/visitors/:id" element={page(VisitorFile)} />
            <Route path="files/rahkaran" element={page(RahkaranList)} />
            <Route path="files/rahkaran/:code" element={page(RahkaranFile)} />
            <Route path="finance/:view" element={page(FinanceView)} />
            <Route path="reconciliation" element={page(Reconciliation)} />
            <Route path="reports" element={page(ExcelReports)} />
            <Route element={<SalesFrame />}>
              <Route path="sales" element={page(SalesOverview)} />
              <Route path="hybrid" element={page(Hybrid)} />
              <Route path="team" element={page(Team)} />
              <Route path="products" element={page(Products)} />
              <Route path="customers" element={page(Customers)} />
              <Route path="analysis" element={page(Analysis)} />
              <Route path="inventory" element={page(Inventory)} />
              <Route path="commission" element={page(Commission)} />
              <Route path="contest" element={page(Contest)} />
              <Route path="rahkaran" element={page(Rahkaran)} />
              <Route path="rahkaran/customer-brand" element={page(RahkaranReports, 'CustomerBrand')} />
              <Route path="rahkaran/total-report" element={page(RahkaranReports, 'TotalReport')} />
              <Route path="rahkaran/compare" element={page(RahkaranCompare)} />
              <Route path="rahkaran/reorder" element={page(Reorder)} />
              <Route path="rahkaran/export" element={page(Export)} />
              <Route path="rahkaran/commission" element={page(RahkaranCommission)} />
              <Route path="detail/:dim/:key" element={page(Detail)} />
              <Route path="data" element={page(DataSource)} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AppProvider>
    </AuthGate>
  </React.StrictMode>,
)
