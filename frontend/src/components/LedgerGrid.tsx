"use client";
/** The ledger as an AG Grid (Community edition only: SPEC 11 screen 12). Logic lives in `lib/ledger.ts`; this is the thin view. */
import { AllCommunityModule, ModuleRegistry, themeQuartz, type ColDef, type ICellRendererParams, type RowClassParams } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useMemo } from "react";
import { MATCH_SYMBOL, amountText, shortRef, totalsRow, typeLabel } from "@/lib/ledger";
import { formatMoney } from "@/lib/money";
import { formatDateTime } from "@/lib/time";
import type { LedgerRow, MatchResponse } from "@/lib/types";

ModuleRegistry.registerModules([AllCommunityModule]);

const isTotals = (r?: LedgerRow) => r?.type === "TOTALS";

export type Matches = MatchResponse["results"] | null;

export function LedgerGrid({ rows, balanceCents, matches, quickFilter, onOpenMeta }: {
  rows: LedgerRow[]; balanceCents: number; matches: Matches; quickFilter: string; onOpenMeta: (row: LedgerRow) => void;
}) {
  const columns = useMemo<ColDef<LedgerRow>[]>(() => [
    { field: "seq", headerName: "#", width: 80, pinned: "left", valueFormatter: (p) => (isTotals(p.data) ? "" : String(p.value)), sort: "asc" },
    { field: "created_at", headerName: "Time", width: 150, valueFormatter: (p) => (p.value ? formatDateTime(p.value) : "") },
    { field: "bucket", headerName: "Bucket", width: 100, valueFormatter: (p) => (p.value === "POOL" ? "Pool" : p.value === "NONE" ? "Memo" : "") },
    { field: "type", headerName: "Type", width: 190, valueFormatter: (p) => (p.value === "TOTALS" ? "Totals" : typeLabel(p.value)) },
    { field: "counterparty", headerName: "Counterparty", width: 190, valueFormatter: (p) => p.value ?? "" },
    {
      field: "amount_cents", headerName: "Amount", width: 130, type: "rightAligned",
      valueFormatter: (p) => (isTotals(p.data) ? formatMoney(p.value) : amountText(p.value)),
      cellClass: (p) => (p.value < 0 ? "text-red-700" : p.value > 0 ? "text-green-700" : "text-gray-400"),
    },
    { field: "running_balance_cents", headerName: "Pool balance", width: 140, type: "rightAligned", valueFormatter: (p) => formatMoney(p.value) },
    { field: "status", headerName: "Status", width: 120, valueFormatter: (p) => p.value ?? "" },
    {
      field: "paypal_ref", headerName: "PayPal ref", width: 140,
      cellRenderer: (p: ICellRendererParams<LedgerRow>) => (p.value ? <span title={p.value}>{shortRef(p.value)}</span> : null),   // full reference on hover; search still sees it whole
    },
    { field: "actor_name", headerName: "By", width: 150 },
    {
      colId: "match", headerName: "PayPal match", width: 130,
      valueGetter: (p) => (p.data && !isTotals(p.data) && matches ? matches[String(p.data.seq)]?.status ?? "" : ""),
      cellRenderer: (p: ICellRendererParams<LedgerRow>) => {
        const m = p.data && matches ? matches[String(p.data.seq)] : undefined;
        if (!m) return null;
        const s = MATCH_SYMBOL[m.status];
        return <span title={`${s.label}. ${m.detail}`} aria-label={s.label}>{s.symbol}</span>;
      },
    },
    {
      colId: "meta", headerName: "", width: 90, sortable: false, filter: false,
      cellRenderer: (p: ICellRendererParams<LedgerRow>) =>
        p.data && !isTotals(p.data) ? <button className="text-sea-700 underline" onClick={() => onOpenMeta(p.data!)}>Details</button> : null,
    },
  ], [matches, onOpenMeta]);

  const pinned = useMemo(() => [totalsRow(rows, balanceCents)], [rows, balanceCents]);
  return (
    <div className={rows.length > 200 ? "h-[600px]" : ""} data-testid="ledger-grid">
      <AgGridReact<LedgerRow>
        theme={themeQuartz}
        rowData={rows}
        columnDefs={columns}
        defaultColDef={{ sortable: true, filter: true, resizable: true }}
        pinnedBottomRowData={pinned}
        quickFilterText={quickFilter}
        domLayout={rows.length > 200 ? "normal" : "autoHeight"}
        suppressColumnVirtualisation
        getRowId={(p) => String(p.data.seq)}
        getRowClass={(p: RowClassParams<LedgerRow>) => (isTotals(p.data) ? "font-semibold" : p.data?.alert ? "bg-red-50" : undefined)}
        overlayNoRowsTemplate="No ledger rows match"
      />
    </div>
  );
}
