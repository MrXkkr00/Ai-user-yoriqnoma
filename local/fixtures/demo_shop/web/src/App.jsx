import { Outlet, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import { RequireAdmin, RequireAuth, RequireRole } from "./components/guards.jsx";
import { Catalog, Home, NotFound, Product } from "./pages/public.jsx";
import { ForgotPassword, Login, Register, VerifyEmail } from "./pages/auth.jsx";
import {
  AccountDelete,
  Dashboard,
  Messages,
  OrderDetail,
  OrderNew,
  Orders,
  Profile,
  Settings,
} from "./pages/cabinet.jsx";
import { CourierOrder, CourierOrders, StaffOrder, StaffOrders } from "./pages/staff.jsx";
import { AdminHome, AdminRefund, AdminRoles, AdminUsers } from "./pages/admin.jsx";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="catalog" element={<Catalog />} />
        <Route path="catalog/:id" element={<Product />} />
        <Route path="register" element={<Register />} />
        <Route path="login" element={<Login />} />
        <Route path="verify-email" element={<VerifyEmail />} />
        <Route path="forgot-password" element={<ForgotPassword />} />

        <Route
          path="app"
          element={
            <RequireAuth>
              <Outlet />
            </RequireAuth>
          }
        >
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="profile" element={<Profile />} />
          <Route path="settings" element={<Settings />} />
          <Route path="orders" element={<RequireRole role="customer"><Orders /></RequireRole>} />
          <Route path="orders/new" element={<RequireRole role="customer"><OrderNew /></RequireRole>} />
          <Route path="orders/:id" element={<RequireRole role="customer"><OrderDetail /></RequireRole>} />
          <Route path="messages" element={<RequireRole role="customer"><Messages /></RequireRole>} />
          <Route
            path="account/delete"
            element={<RequireRole role="customer"><AccountDelete /></RequireRole>}
          />
        </Route>

        <Route path="staff/orders" element={<RequireRole role="manager"><StaffOrders /></RequireRole>} />
        <Route path="staff/orders/:id" element={<RequireRole role="manager"><StaffOrder /></RequireRole>} />
        <Route path="courier" element={<RequireRole role="courier"><CourierOrders /></RequireRole>} />
        <Route
          path="courier/orders/:id"
          element={<RequireRole role="courier"><CourierOrder /></RequireRole>}
        />

        <Route path="admin" element={<RequireAdmin><AdminHome /></RequireAdmin>} />
        <Route path="admin/users" element={<RequireAdmin><AdminUsers /></RequireAdmin>} />
        <Route path="admin/roles" element={<RequireAdmin><AdminRoles /></RequireAdmin>} />
        <Route path="admin/orders/:id/refund" element={<RequireAdmin><AdminRefund /></RequireAdmin>} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
