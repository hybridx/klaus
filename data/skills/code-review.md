## Code Review

A structured approach to reviewing code for quality, correctness, and maintainability.

### Procedure

1. **Read the diff** — understand what changed and why
2. **Check correctness** — does the logic do what it claims?
3. **Look for edge cases** — empty inputs, off-by-one, null/None handling
4. **Evaluate naming** — are variables, functions, and classes named clearly?
5. **Check error handling** — are exceptions caught appropriately?
6. **Assess performance** — any obvious O(n^2) where O(n) is possible?
7. **Verify tests** — are the changes covered by tests?
8. **Summarize** — provide clear, actionable feedback with line references
