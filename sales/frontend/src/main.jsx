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
import Inventory from './pages/Inventory.jsx'
import Rahkaran from './pages/Rahkaran.jsx'
import { CustomerBrand, TotalReport } from './pages/RahkaranReports.jsx'
import Export from './pages/Export.jsx'
import RahkaranCompare from './pages/RahkaranCompare.jsx'
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
            <Route path="inventory" element={<Inventory />} />
            <Route path="rahkaran" element={<Rahkaran />} />
            <Route path="rahkaran/customer-brand" element={<CustomerBrand />} />
            <Route path="rahkaran/total-report" element={<TotalReport />} />
            <Route path="rahkaran/compare" element={<RahkaranCompare />} />
            <Route path="rahkaran/export" element={<Export />} />
            <Route path="detail/:dim/:key" element={<Detail />} />
            <Route path="data" element={<DataSource />} />
            <Route path="*" element={<Overview />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AppProvider>
  </React.StrictMode>,
)
