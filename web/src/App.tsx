import { Routes, Route, Navigate, useOutletContext } from "react-router";
import { Toaster } from "@/components/ui/sonner";
import { LocationProvider } from "@/lib/location";
import { AppShell } from "@/components/shell";
import { useAuth } from "@/hooks/useAuth";
import { api as trpc } from "@/lib/api";
import Home from "@/pages/customer/Home";
import SearchFlow from "@/pages/customer/SearchFlow";
import Browse from "@/pages/customer/Browse";
import ShopDetail from "@/pages/customer/ShopDetail";
import Compare from "@/pages/customer/Compare";
import History from "@/pages/customer/History";
import Account from "@/pages/Account";
import Inbox from "@/pages/merchant/Inbox";
import Inventory from "@/pages/merchant/Inventory";
import Khata from "@/pages/merchant/Khata";
import Demand from "@/pages/merchant/Demand";
import Login from "@/pages/Login";
import Onboarding from "@/pages/Onboarding";
import NotFound from "@/pages/NotFound";

export function useRole() {
  return useOutletContext<{ role: "customer" | "shopkeeper" }>();
}

function RoleHome() {
  const { isAuthenticated } = useAuth();
  const profile = trpc.profile.get.useQuery(undefined, { enabled: isAuthenticated });
  if (profile.data?.appRole === "shopkeeper") {
    return <Navigate to={profile.data.shop ? "/merchant" : "/onboarding"} replace />;
  }
  return <Home />;
}

export default function App() {
  return (
    <LocationProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/onboarding" element={<Onboarding />} />
        <Route element={<AppShell />}>
          <Route path="/" element={<RoleHome />} />
          <Route path="/search" element={<SearchFlow />} />
          <Route path="/browse" element={<Browse />} />
          <Route path="/shop/:id" element={<ShopDetail />} />
          <Route path="/compare" element={<Compare />} />
          <Route path="/history" element={<History />} />
          <Route path="/account" element={<Account />} />
          <Route path="/merchant" element={<Inbox />} />
          <Route path="/merchant/inventory" element={<Inventory />} />
          <Route path="/merchant/khata" element={<Khata />} />
          <Route path="/merchant/demand" element={<Demand />} />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Routes>
      <Toaster position="top-center" richColors />
    </LocationProvider>
  );
}
