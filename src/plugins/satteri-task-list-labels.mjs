// Gives GitHub-style task-list checkboxes an accessible name. Markdown produces disabled
// `<input type="checkbox">` elements with no label, which axe-core reports as a critical
// WCAG 2.1 "form elements must have labels" violation, and which leaves assistive
// technology without the completed/outstanding state the checkbox conveys visually.
export default function taskListLabels() {
  return {
    name: "micboard-task-list-labels",
    element: {
      filter: ["input"],
      visit(node, context) {
        const properties = node.properties ?? {};
        if (properties.type !== "checkbox" || !properties.disabled) return;
        if (properties.ariaLabel || properties["aria-label"]) return;
        context.setProperty(node, "ariaLabel", properties.checked ? "Completed" : "Not completed");
      },
    },
  };
}
