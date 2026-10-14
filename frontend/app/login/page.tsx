import type { Metadata } from "next";
import { AuthForm } from "@/components/AuthForm";
export const metadata: Metadata = { title: "Log in", robots: { index: false } };
export default function Page() { return <div className="section"><AuthForm /></div>; }
