import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import 'vazirmatn/Vazirmatn-font-face.css'
import './styles.css'
import { AppProvider } from './lib.jsx'
import Layout from './components/Layout.jsx'
import Overview from './pages/Overview.jsx'
import Hybrid from './pages/Hybrid.jsx'
import Team from './pages/Team.jsx'
import Products from './pages/Products.jsx'
import Customers from './pages/Customers.jsx'
import Analysis from './pages/Analysis.jsx'
import Detail from './pages/Detail.jsx'
import DataSource from './pages/DataSource.jsx'
import Plan from './pages/Plan.jsx'
import Commission from './pages/Commission.jsx'
import Contest from './pages/Contest.jsx'
import Inventory from './pages/Inventory.jsx'
import Rahkaran from './pages/Rahkaran.jsx'
import { Overview as B2BOverview, Performance as B2BPerformance, Products as B2BProducts, Analysis as B2BAnalysis, Orders as B2BOrders } from './pages/B2BWorkspace.jsx'
import { CustomerBrand, TotalReport } from './pages/RahkaranReports.jsx'
import Export from './pages/Export.jsx'
import ExportPreview from './pages/ExportPreview.jsx'
import RahkaranCompare from './pages/RahkaranCompare.jsx'
import Reorder from './pages/Reorder.jsx'
import RahkaranCommission from './pages/RahkaranCommission.jsx'
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <AppProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Overview />} />
            <Route path="hybrid" element={<Hybrid />} />
            <Route path="team" element={<Team />} />
            <Route path="products" element={<Products />} />
            <Route path="customers" element={<Customers />} />
            <Route path="analysis" element={<Analysis />} />
            <Route path="plan" element={<Plan />} />
            <Route path="commission" element={<Commission />} />
            <Route path="contest" element={<Contest />} />
            <Route path="inventory" element={<Inventory />} />
            <Route path="rahkaran" element={<Rahkaran />} />
            <Route path="rahkaran/overview" element={<B2BOverview />} />
            <Route path="rahkaran/performance" element={<B2BPerformance />} />
            <Route path="rahkaran/products" element={<B2BProducts />} />
            <Route path="rahkaran/analysis" element={<B2BAnalysis />} />
            <Route path="rahkaran/orders" element={<B2BOrders />} />
            <Route path="rahkaran/customer-brand" element={<CustomerBrand />} />
            <Route path="rahkaran/total-report" element={<TotalReport />} />
            <Route path="rahkaran/compare" element={<RahkaranCompare />} />
            <Route path="rahkaran/reorder" element={<Reorder />} />
            <Route path="rahkaran/export" element={<ExportPreview />} />
            <Route path="rahkaran/export/preview" element={<ExportPreview />} />
            <Route path="rahkaran/commission" element={<RahkaranCommission />} />
            <Route path="detail/:dim/:key" element={<Detail />} />
            <Route path="data" element={<DataSource />} />
            <Route path="*" element={<Overview />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AppProvider>
  </React.StrictMode>,
)
