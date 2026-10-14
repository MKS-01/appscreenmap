// `import x from "….css" with { type: "text" }` gives the file's text (Bun text import).
declare module "*.css" {
  const text: string;
  export default text;
}
