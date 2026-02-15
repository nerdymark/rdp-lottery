import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './components/Dashboard'
import SubnetManager from './components/SubnetManager'
import HostTable from './components/HostTable'
import HostDetail from './components/HostDetail'
import ScanHistory from './components/ScanHistory'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/subnets" element={<SubnetManager />} />
        <Route path="/hosts" element={<HostTable />} />
        <Route path="/hosts/:id" element={<HostDetail />} />
        <Route path="/scans" element={<ScanHistory />} />
      </Routes>
    </Layout>
  )
}
