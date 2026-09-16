"use client";
import { useState, useEffect } from "react";
import { Check } from "lucide-react";
import { RequireAuth } from "@/components/RequireAuth";
import { PageHeader, Skeleton, ErrorNote } from "@/components/ui";
import { useToast } from "@/components/Toast";
import { API_BASE, getToken } from "@/lib/api";

interface Plan {
  id: string;
  name: string;
  slug: string;
  description: string;
  price_monthly: number;
  price_yearly: number;
  seat_limit: number;
  features: string[];
  max_questions: number;
  max_exams_per_day: number;
  has_proctoring: boolean;
  has_analytics: boolean;
  has_custom_branding: boolean;
  has_api_access: boolean;
  is_active: boolean;
  is_default: boolean;
}

export default function PlansPage() {
  return (
    <RequireAuth roles={["student"]}>
      <Plans />
    </RequireAuth>
  );
}

function Plans() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [subscribing, setSubscribing] = useState<string | null>(null);
  const [billing, setBilling] = useState<"monthly" | "yearly">("monthly");
  const { toast } = useToast();

  useEffect(() => {
    const loadPlans = async () => {
      try {
        const token = getToken();
        const res = await fetch(`${API_BASE}/student/plans`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (res.ok) {
          const data = await res.json();
          setPlans(data.filter((p: Plan) => p.is_active));
        }
      } catch {
        setError("Failed to load plans");
      } finally {
        setLoading(false);
      }
    };
    loadPlans();
  }, []);

  const handleSubscribe = async (planId: string, planName: string) => {
    setSubscribing(planId);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/student/subscribe`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ plan_id: planId }),
      });
      if (res.ok) {
        toast("success", `Subscribed to ${planName} successfully!`);
      } else {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to subscribe");
      }
    } catch (e: any) {
      toast("error", e.message || "Failed to subscribe");
    } finally {
      setSubscribing(null);
    }
  };

  if (loading) return <Skeleton rows={4} />;
  if (error) return <ErrorNote message={error} />;

  const getAccentColor = (plan: Plan) => {
    if (plan.is_default) return "#059669";
    const slug = plan.slug.toLowerCase();
    if (slug.includes("enterprise") || slug.includes("custom")) return "#c026d3";
    if (slug.includes("pro") || slug.includes("premium")) return "#059669";
    if (slug.includes("starter") || slug.includes("basic")) return "#0891b2";
    return "var(--primary)";
  };

  const getSavings = (plan: Plan) => {
    if (!plan.price_yearly || !plan.price_monthly) return 0;
    return Math.round((1 - plan.price_yearly / (plan.price_monthly * 12)) * 100);
  };

  const hasPaidPlans = plans.some((p) => p.price_monthly > 0);
  const maxSavings = hasPaidPlans ? Math.max(...plans.map(getSavings)) : 0;

  return (
    <>
      <PageHeader
        title="Pricing Plans"
        sub="Choose a plan that works for you. Upgrade anytime."
      />

      {hasPaidPlans && (
        <div className="pricing-billing-toggle">
          <button
            onClick={() => setBilling("monthly")}
            className={`pricing-billing-btn ${billing === "monthly" ? "pricing-billing-btn-active" : "pricing-billing-btn-inactive"}`}
            style={{ background: billing === "monthly" ? "var(--primary)" : undefined }}
          >
            Monthly
          </button>
          <button
            onClick={() => setBilling("yearly")}
            className={`pricing-billing-btn ${billing === "yearly" ? "pricing-billing-btn-active" : "pricing-billing-btn-inactive"}`}
            style={{ background: billing === "yearly" ? "var(--primary)" : undefined }}
          >
            Yearly
            {maxSavings > 0 && (
              <span className="pricing-billing-save">
                Save up to {maxSavings}%
              </span>
            )}
          </button>
        </div>
      )}

      <div className="pricing-plans">
        {plans.map((plan) => {
          const accent = getAccentColor(plan);
          const isFeatured = plan.is_default;
          const price = billing === "yearly" && plan.price_yearly > 0
            ? plan.price_yearly
            : plan.price_monthly;
          const isYearly = billing === "yearly" && plan.price_yearly > 0;
          const savings = getSavings(plan);

          return (
            <div
              key={plan.id}
              className={`pricing-card ${isFeatured ? "pricing-featured" : ""}`}
              style={{ borderColor: isFeatured ? accent : undefined }}
              onMouseEnter={(e) => {
                if (!isFeatured) e.currentTarget.style.borderColor = accent;
              }}
              onMouseLeave={(e) => {
                if (!isFeatured) e.currentTarget.style.borderColor = "";
              }}
            >
              <div className="pricing-heading" style={{ color: accent }}>
                <h4 style={{ color: accent }}>{plan.name}</h4>
                <p>{plan.description}</p>
              </div>

              <div>
                {price === 0 ? (
                  <div className="pricing-price" style={{ color: accent }}>Free</div>
                ) : (
                  <>
                    <div className="pricing-price" style={{ color: accent }}>
                      {'\u20B9'}{price.toLocaleString()}
                    </div>
                    <div className="pricing-price-sub">
                      /mo{isYearly ? " (billed yearly)" : ""}
                    </div>
                  </>
                )}
              </div>

              {isYearly && savings > 0 && (
                <div
                  className="pricing-savings"
                  style={{ background: `${accent}18`, color: accent }}
                >
                  Save {savings}% vs monthly
                </div>
              )}

              <ul className="pricing-features">
                {plan.features.map((feature, i) => (
                  <li key={i}>
                    <Check size={14} style={{ color: accent, flexShrink: 0, marginTop: 2 }} />
                    <span>{feature}</span>
                  </li>
                ))}
                {plan.max_questions > 0 && (
                  <li>
                    <Check size={14} style={{ color: accent, flexShrink: 0, marginTop: 2 }} />
                    <span><strong>{plan.max_questions.toLocaleString()}</strong> questions</span>
                  </li>
                )}
                {plan.max_exams_per_day > 0 && (
                  <li>
                    <Check size={14} style={{ color: accent, flexShrink: 0, marginTop: 2 }} />
                    <span><strong>{plan.max_exams_per_day}</strong> exams/day</span>
                  </li>
                )}
                {plan.seat_limit > 0 && (
                  <li>
                    <Check size={14} style={{ color: accent, flexShrink: 0, marginTop: 2 }} />
                    <span><strong>{plan.seat_limit.toLocaleString()}</strong> seats</span>
                  </li>
                )}
                {plan.has_proctoring && (
                  <li>
                    <Check size={14} style={{ color: accent, flexShrink: 0, marginTop: 2 }} />
                    <span><strong>Proctoring</strong> included</span>
                  </li>
                )}
                {plan.has_analytics && (
                  <li>
                    <Check size={14} style={{ color: accent, flexShrink: 0, marginTop: 2 }} />
                    <span><strong>Analytics</strong> dashboard</span>
                  </li>
                )}
                {plan.has_custom_branding && (
                  <li>
                    <Check size={14} style={{ color: accent, flexShrink: 0, marginTop: 2 }} />
                    <span><strong>Custom</strong> branding</span>
                  </li>
                )}
                {plan.has_api_access && (
                  <li>
                    <Check size={14} style={{ color: accent, flexShrink: 0, marginTop: 2 }} />
                    <span><strong>API</strong> access</span>
                  </li>
                )}
              </ul>

              <button
                className="pricing-cta"
                style={{ borderColor: accent, background: accent, color: "#fff" }}
                onClick={() => handleSubscribe(plan.id, plan.name)}
                disabled={subscribing === plan.id}
                onMouseEnter={(e) => {
                  if (subscribing !== plan.id) {
                    e.currentTarget.style.background = "transparent";
                    e.currentTarget.style.color = accent;
                  }
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = accent;
                  e.currentTarget.style.color = "#fff";
                }}
              >
                {subscribing === plan.id
                  ? "Subscribing..."
                  : price === 0
                    ? "Get Started"
                    : "Subscribe Now"}
              </button>
            </div>
          );
        })}
      </div>

      {plans.length === 0 && !loading && (
        <div className="ds-card p-8 text-center text-muted">
          No plans available at the moment. Please check back later.
        </div>
      )}
    </>
  );
}
