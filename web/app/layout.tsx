import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Book Reel Generator",
  description: "Type a book name. Get a 30-second Instagram Reel summary.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
