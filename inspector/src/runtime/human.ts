export type HumanSchema = Record<string, unknown>;

export type HumanField = {
  name: string;
  title: string;
  description: string | undefined;
  type: "string" | "number" | "integer" | "boolean" | "array";
  required: boolean;
  itemsType: "string" | undefined;
  minLength?: number;
  maxLength?: number;
  minItems?: number;
  maxItems?: number;
  itemMinLength?: number;
  itemMaxLength?: number;
  minimum?: number;
  maximum?: number;
};

export type HumanDecisionOptions = {
  allowedValues?: Record<string, string[]>;
};

export function getHumanInputFields(schema: HumanSchema | undefined): HumanField[] | null {
  if (!schema || schema.type !== "object" || !isRecord(schema.properties)) return null;
  const properties = schema.properties;
  const required = new Set(
    Array.isArray(schema.required)
      ? schema.required.filter((value): value is string => typeof value === "string")
      : [],
  );
  if (
    schema.required !== undefined &&
    !Array.isArray(schema.required)
  ) return null;
  if ([...required].some((name) => !Object.prototype.hasOwnProperty.call(properties, name))) {
    return null;
  }
  const fields: HumanField[] = [];
  for (const [name, raw] of Object.entries(properties)) {
    if (!isRecord(raw)) return null;
    const type = raw.type;
    if (type === "string" || type === "number" || type === "integer" || type === "boolean") {
      if (!hasOnlyKeys(raw, [
        "type",
        "title",
        "description",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
      ])) return null;
      if (!isOptionalNonNegativeNumber(raw.minLength) || !isOptionalNonNegativeNumber(raw.maxLength)) return null;
      if (
        (type === "string" && (!isOptionalNonNegativeNumber(raw.minLength) || !isOptionalNonNegativeNumber(raw.maxLength))) ||
        (type !== "string" && (raw.minLength !== undefined || raw.maxLength !== undefined)) ||
        (type === "string" && (raw.minimum !== undefined || raw.maximum !== undefined)) ||
        (type !== "string" && (!isOptionalBound(raw.minimum) || !isOptionalBound(raw.maximum)))
      ) return null;
      fields.push({
        name,
        title: typeof raw.title === "string" ? raw.title : name,
        description: typeof raw.description === "string" ? raw.description : undefined,
        type,
        required: required.has(name),
        itemsType: undefined,
        ...(type !== "string" && typeof raw.minimum === "number"
          ? { minimum: raw.minimum }
          : {}),
        ...(type !== "string" && typeof raw.maximum === "number"
          ? { maximum: raw.maximum }
          : {}),
        ...(type === "string" && typeof raw.minLength === "number" ? { minLength: raw.minLength } : {}),
        ...(type === "string" && typeof raw.maxLength === "number" ? { maxLength: raw.maxLength } : {}),
      });
      continue;
    }
    if (
      type === "array" &&
      isRecord(raw.items) &&
      raw.items.type === "string"
    ) {
      if (!hasOnlyKeys(raw, [
        "type",
        "title",
        "description",
        "minItems",
        "maxItems",
        "items",
      ]) ||
        !hasOnlyKeys(raw.items, ["type", "minLength", "maxLength"]) ||
        !isOptionalNonNegativeNumber(raw.minItems) ||
        !isOptionalNonNegativeNumber(raw.maxItems) ||
        !isOptionalNonNegativeNumber(raw.items.minLength) ||
        !isOptionalNonNegativeNumber(raw.items.maxLength)
      ) return null;
      fields.push({
        name,
        title: typeof raw.title === "string" ? raw.title : name,
        description: typeof raw.description === "string" ? raw.description : undefined,
        type,
        required: required.has(name),
        itemsType: "string",
        ...(typeof raw.minItems === "number" ? { minItems: raw.minItems } : {}),
        ...(typeof raw.maxItems === "number" ? { maxItems: raw.maxItems } : {}),
        ...(typeof raw.items.minLength === "number" ? { itemMinLength: raw.items.minLength } : {}),
        ...(typeof raw.items.maxLength === "number" ? { itemMaxLength: raw.items.maxLength } : {}),
      });
      continue;
    }
    return null;
  }
  return fields;
}

export function coerceHumanField(field: HumanField, value: string): unknown {
  if (field.type === "boolean") return value === "true";
  if (field.type === "number") return Number(value);
  if (field.type === "integer") return Number(value);
  if (field.type === "array") {
    return value
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return value;
}

export function buildHumanInputDecision(
  fields: HumanField[],
  values: Record<string, string>,
  options: HumanDecisionOptions = {},
): { decision: Record<string, unknown> | null; errors: string[] } {
  const decision: Record<string, unknown> = {};
  const errors: string[] = [];

  for (const field of fields) {
    const rawValue = values[field.name];
    if (field.type === "boolean") {
      if (rawValue === undefined || rawValue === "") {
        if (field.required) errors.push(`${field.title} 必须填写`);
      } else if (rawValue !== "true" && rawValue !== "false") {
        errors.push(`${field.title} 必须选择是或否`);
      } else {
        decision[field.name] = coerceHumanField(field, rawValue);
      }
      continue;
    }
    if (rawValue === undefined || rawValue === "") {
      if (field.required) errors.push(`${field.title} 必须填写`);
      continue;
    }

    const value = coerceHumanField(field, rawValue);
    if (field.type === "number" || field.type === "integer") {
      if (
        rawValue.trim() === "" ||
        typeof value !== "number" ||
        !Number.isFinite(value) ||
        (field.type === "integer" && !Number.isInteger(value))
      ) {
        errors.push(`${field.title} 必须是有效数字`);
        continue;
      }
      if (field.minimum !== undefined && value < field.minimum) {
        errors.push(`${field.title} 不能小于 ${field.minimum}`);
      }
      if (field.maximum !== undefined && value > field.maximum) {
        errors.push(`${field.title} 不能大于 ${field.maximum}`);
      }
    }
    if (field.type === "array" && Array.isArray(value)) {
      if (field.required && value.length === 0) errors.push(`${field.title} 不能为空`);
      if (field.minItems !== undefined && value.length < field.minItems) {
        errors.push(`${field.title} 至少需要 ${field.minItems} 项`);
      }
      if (field.maxItems !== undefined && value.length > field.maxItems) {
        errors.push(`${field.title} 最多允许 ${field.maxItems} 项`);
      }
      if (
        value.some((item) =>
          (field.itemMinLength !== undefined && item.length < field.itemMinLength) ||
          (field.itemMaxLength !== undefined && item.length > field.itemMaxLength)
        )
      ) {
        errors.push(`${field.title} 中有文本长度不符合要求`);
      }
      const allowedValues = options.allowedValues?.[field.name];
      if (allowedValues && value.some((item) => !allowedValues.includes(item))) {
        errors.push(`${field.title} 包含未登记或不可引用的产物`);
      }
    }
    if (field.type === "string") {
      if (field.minLength !== undefined && rawValue.length < field.minLength) {
        errors.push(`${field.title} 至少需要 ${field.minLength} 个字符`);
      }
      if (field.maxLength !== undefined && rawValue.length > field.maxLength) {
        errors.push(`${field.title} 最多允许 ${field.maxLength} 个字符`);
      }
    }
    decision[field.name] = value;
  }

  return { decision: errors.length === 0 ? decision : null, errors };
}

export function isArtifactReferenceField(field: HumanField): boolean {
  return field.type === "array" &&
    field.itemsType === "string" &&
    (field.name === "artifact_refs" || field.name === "artifactRefs");
}

export function createHumanDecisionIdempotencyKey(
  requestId: string,
  version: number,
  payload: { choice?: string; decision?: unknown; comment?: string },
): string {
  const source = `${requestId}:${version}:${stableStringify(payload)}`;
  let hash = 14695981039346656037n;
  for (let index = 0; index < source.length; index += 1) {
    hash ^= BigInt(source.charCodeAt(index));
    hash = BigInt.asUintN(64, hash * 1099511628211n);
  }
  return `inspector-${requestId}-${version}-${hash.toString(16).padStart(16, "0")}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasOnlyKeys(value: Record<string, unknown>, allowed: string[]): boolean {
  return Object.keys(value).every((key) => allowed.includes(key));
}

function isOptionalNonNegativeNumber(value: unknown): boolean {
  return value === undefined || (typeof value === "number" && Number.isFinite(value) && value >= 0);
}

function isOptionalBound(value: unknown): boolean {
  return value === undefined || (typeof value === "number" && Number.isFinite(value));
}

function stableStringify(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  if (isRecord(value)) {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}
