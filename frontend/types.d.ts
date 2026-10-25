export type ExperienceMode = 'simple' | 'smart' | 'advanced';
export type MerchantCategory =
  | 'street vendor'
  | 'kirana or general store'
  | 'food stall or small eatery'
  | 'clothing or accessories shop'
  | 'home-based business'
  | 'other';

export interface Merchant {
  id: string;
  name: string;
  category: string;
  onboarding: Record<string, string>;
  products: Product[];
  sales: Sale[];
  expenses: Expense[];
  transactions: Transaction[];
  campaigns: Campaign[];
  tasks: AutopilotTask[];
  scenarios: BusinessScenario[];
}

export interface Product {
  id: string;
  name: string;
  category?: string;
  quantity: number | null;
  cost: number | null;
  price: number | null;
}

export interface Sale {
  id: string;
  date: string;
  amount: number;
  quantity: number;
  unitPrice: number | null;
  productId?: string;
  productName?: string;
  costOfGoods: number | null;
  note: string;
  source: 'user' | 'demo';
}

export interface Expense {
  id: string;
  date: string;
  amount: number;
  category: string;
  note: string;
  source: 'user' | 'demo';
}

export type Transaction =
  | ({ type: 'sale' } & Sale)
  | ({ type: 'expense' } & Expense);

export interface InventoryItem {
  productId: string;
  quantity: number | null;
  countedAt?: string;
}

export interface BusinessScenario {
  id: string;
  quantity: number;
  cost: number;
  price: number;
  inventory: number;
  demand: number;
  period: number;
  discount: number;
  savedAt: string;
  outcomes: ScenarioProjection;
}

export interface ScenarioProjection {
  inventory: number;
  units: number;
  revenue: number;
  cogs: number;
  grossProfit: number;
  unsold: number;
  unsoldValue: number;
}

export interface AIRecommendation {
  title: string;
  message: string;
  evidence: string[];
  nextAction?: { label: string; page: string; dialog?: string };
}

export interface Campaign {
  id: string;
  productId: string;
  productName: string;
  objective: string;
  copy: string;
  status: 'draft';
  createdAt: string;
}

export interface AutopilotTask {
  id: string;
  title: string;
  goal: string;
  completed: boolean;
  approved: boolean;
  requiresApproval: boolean;
}
