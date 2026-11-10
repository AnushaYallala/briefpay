"use client";
/** The steps of one money plan as an AG Grid (Community only). Logic lives in `lib/plans.ts`; this is the thin view. */
import { AllCommunityModule, ModuleRegistry, themeQuartz, type ColDef, type ICellRendererParams } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { Badge } from "@/components/ui";
import { shortRef } from "@/lib/ledger";
import { formatMoney } from "@/lib/money";
import { opWord, stepState } from "@/lib/plans";
import type { PlanStep } from "@/lib/types";

ModuleRegistry.registerModules([AllCommunityModule]);

const titleCase = (s: string) => s.charAt(0) + s.slice(1).toLowerCase();

const COLUMNS: ColDef<PlanStep>[] = [
  { field: "seq", headerName: "#", width: 70, pinned: "left", sort: "asc" },
  { field: "phase", headerName: "Phase", width: 90 },
  { field: "op", headerName: "What", width: 170, valueFormatter: (p) => opWord(p.value) },
  { colId: "target", headerName: "About", width: 140, valueGetter: (p) => (p.data ? `${titleCase(p.data.target_type)} ${p.data.target_id}` : "") },
  { field: "amount_cents", headerName: "Amount", width: 120, type: "rightAligned", valueFormatter: (p) => formatMoney(p.value) },
  { field: "bucket", headerName: "Bucket", width: 100, valueFormatter: (p) => (p.value === "POOL" ? "Pool" : "Memo") },
  { field: "receiver_email", headerName: "Receiver", width: 220, valueFormatter: (p) => p.value ?? "" },
  {
    field: "state", headerName: "State", width: 210,
    cellRenderer: (p: ICellRendererParams<PlanStep>) => <Badge tone={stepState(p.value).tone}>{stepState(p.value).label}</Badge>,
  },
  { field: "paypal_ref", headerName: "PayPal ref", width: 140, cellRenderer: (p: ICellRendererParams<PlanStep>) => (p.value ? <span title={p.value}>{shortRef(p.value)}</span> : null) },
  { field: "error", headerName: "Problem", width: 220, valueFormatter: (p) => (p.value ? JSON.stringify(p.value) : ""), tooltipValueGetter: (p) => (p.value ? JSON.stringify(p.value) : "") },
];

export function StepsGrid({ steps }: { steps: PlanStep[] }) {
  return (
    <div data-testid="steps-grid">
      <AgGridReact<PlanStep>
        theme={themeQuartz}
        rowData={steps}
        columnDefs={COLUMNS}
        defaultColDef={{ sortable: true, filter: true, resizable: true }}
        domLayout="autoHeight"
        suppressColumnVirtualisation
        getRowId={(p) => String(p.data.seq)}
        getRowClass={(p) => (p.data?.state === "FAILED" ? "bg-red-50" : undefined)}
        overlayNoRowsTemplate="This plan has no steps"
      />
    </div>
  );
}
