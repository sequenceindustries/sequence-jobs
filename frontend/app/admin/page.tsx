import type { Metadata } from "next";
import { AdminDash } from "@/components/AdminDash";
export const metadata: Metadata = { title: "Admin", robots: { index: false, follow: false } };
export default function Page() { return <AdminDash />; }
