"use client";
import React, { type InputHTMLAttributes, type TextareaHTMLAttributes } from "react";

interface BaseFieldProps {
  label: string;
  hint?: string;
  error?: string | null;
  id?: string;
  required?: boolean;
}

type InputFieldProps = BaseFieldProps & InputHTMLAttributes<HTMLInputElement> & { as?: "input" };
type TextareaFieldProps = BaseFieldProps & TextareaHTMLAttributes<HTMLTextAreaElement> & { as: "textarea"; rows?: number };

export type FormFieldProps = InputFieldProps | TextareaFieldProps;

export function FormField(props: FormFieldProps) {
  const { label, hint, error, id, required, as = "input", className = "", ...rest } = props;
  const autoId = id || `field-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;

  return (
    <div className="space-y-1.5 text-left">
      <div className="flex items-center justify-between">
        <label htmlFor={autoId} className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
          {label}
          {required && <span className="text-red-500 ml-1" title="Required">*</span>}
        </label>
        {hint && !error && <span className="text-2xs text-slate-400 font-normal">{hint}</span>}
      </div>

      {as === "textarea" ? (
        <textarea
          id={autoId}
          required={required}
          className={`input min-h-[80px] ${error ? "border-red-400 focus:border-red-500 focus:shadow-none ring-1 ring-red-400/20" : ""} ${className}`}
          {...(rest as TextareaHTMLAttributes<HTMLTextAreaElement>)}
        />
      ) : (
        <input
          id={autoId}
          required={required}
          className={`input ${error ? "border-red-400 focus:border-red-500 focus:shadow-none ring-1 ring-red-400/20" : ""} ${className}`}
          {...(rest as InputHTMLAttributes<HTMLInputElement>)}
        />
      )}

      {error && (
        <p role="alert" className="text-xs font-semibold text-red-600 mt-1">
          {error}
        </p>
      )}
    </div>
  );
}
