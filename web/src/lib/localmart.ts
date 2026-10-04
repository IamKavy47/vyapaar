// LocalMart shared domain constants (frontend + backend)

export interface CategoryMeta {
  key: string;
  label: string;
  hindi: string;
  color: string; // accent hex
}

export const CATEGORIES: CategoryMeta[] = [
  { key: "kirana", label: "Kirana & Grocery", hindi: "किराना", color: "#E8930C" },
  { key: "vegetables", label: "Sabzi & Fruits", hindi: "सब्ज़ी", color: "#009146" },
  { key: "dairy", label: "Dairy & Bakery", hindi: "दूध", color: "#2BA0FF" },
  { key: "pharmacy", label: "Pharmacy", hindi: "दवाई", color: "#F03749" },
  { key: "hardware", label: "Hardware", hindi: "हार्डवेयर", color: "#8A5A00" },
  { key: "electrical", label: "Electrical", hindi: "बिजली", color: "#7C5CFF" },
  { key: "stationery", label: "Stationery", hindi: "स्टेशनरी", color: "#0E9F8A" },
  { key: "tailor", label: "Tailor & Cloth", hindi: "दर्ज़ी", color: "#E5519E" },
  { key: "mobile", label: "Mobile & Repair", hindi: "मोबाइल", color: "#4A6CF7" },
  { key: "other", label: "Everything Else", hindi: "और भी", color: "#6B6B66" },
];

export function categoryMeta(key: string): CategoryMeta {
  return CATEGORIES.find((c) => c.key === key) ?? CATEGORIES[CATEGORIES.length - 1];
}

export type AppRole = "customer" | "shopkeeper";
export type RequestStatus = "matching" | "offers" | "completed" | "no_match";
export type OfferStatus = "pending" | "accepted" | "declined" | "expired";

export const DEMO_CENTER = { lat: 24.0734, lng: 75.0699, label: "Mandsaur, MP" };
