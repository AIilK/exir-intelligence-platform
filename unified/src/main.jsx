import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import 'vazirmatn/Vazirmatn-font-face.css'
// source apps' global styles — scoped to .sales-scope / .fin-scope at build time
import '@sales/styles.css'
import '@finance/globals.css'
import '@finance/agent.css'
import './unified.css'
import { AppProvider } from '@sales/lib.jsx'
import Shell from './Shell.jsx'
import ManagerOverview from './pages/ManagerOverview.jsx'
import HybridList from './pages/HybridList.jsx'
import HybridFile from './pages/HybridFile.jsx'
import VisitorFile from './pages/VisitorFile.jsx'
import FinanceView from './FinanceView.jsx'
import SalesFrame from './SalesFrame.jsx'
import SalesOverview from '@sales/pages/Overview.jsx'
import Hybrid from '@sales/pages/Hybrid.jsx'
import Team from '@sales/pages/Team.jsx'
import Products from '@sales/pages/Products.jsx'
import Customers from '@sales/pages/Customers.jsx'
import Analysis from '@sales/pages/Analysis.jsx'
import Detail from '@sales/pages/Detail.jsx'
import DataSource from '@sales/pages/DataSource.jsx'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <AppProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Shell />}>
            <Route index element={<ManagerOverview />} />
            <Route path="files/hybrids" element={<HybridList />} />
            <Route path="files/hybrids/:name" element={<HybridFile />} />
            <Route path="files/visitors/:id" element={<VisitorFile />} />
            <Route path="finance/:view" element={<FinanceView />} />
            <Route element={<SalesFrame />}>
              <Route path="sales" element={<SalesOverview />} />
              <Route path="hybrid" element={<Hybrid />} />
              <Route path="team" element={<Team />} />
              <Route path="products" element={<Products />} />
              <Route path="customers" element={<Customers />} />
              <Route path="analysis" element={<Analysis />} />
              <Route path="detail/:dim/:key" element={<Detail />} />
              <Route path="data" element={<DataSource />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AppProvider>
  </React.StrictMode>,
)
