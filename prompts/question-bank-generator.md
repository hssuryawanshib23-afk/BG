You are generating a complete, database-ready BrainGain question bank from chapter content.

## Goal
Return objective, machine-evaluable questions that can be uploaded, validated, ingested, and used for test generation.

## Inputs
1. `CHAPTER_META`
- subject
- grade
- board
- chapter_number
- chapter_name
2. `CHAPTER_TEXT`
- cleaned OCR text for one chapter
3. `DIAGRAM_IMAGES`
- optional list of extracted image filenames or diagram references

## Core Rules
- Extract all teachable concepts from the chapter.
- Merge tiny micro-concepts into a stronger parent concept if they cannot support 6 good questions.
- Do not invent facts beyond the chapter text or provided diagrams.
- Supported formats are `mcq` and `msq` only.
- No free-text answers.
- No ambiguous or duplicate questions.

## Output
Return exactly one JSON object in this shape:

```json
{
  "meta": {
    "subject": "Physics",
    "grade": 9,
    "board": "ICSE",
    "chapter_number": 1,
    "chapter_name": "..."
  },
  "concepts": [
    {
      "name": "...",
      "questions": [
        {
          "id": "CH1_C1_Q1",
          "text": "...",
          "options": [
            { "label": "A", "text": "..." },
            { "label": "B", "text": "..." },
            { "label": "C", "text": "..." },
            { "label": "D", "text": "..." }
          ],
          "answer": ["B"],
          "question_format": "mcq",
          "difficulty": "easy",
          "type": "definition",
          "concept": "...",
          "image": null
        }
      ]
    }
  ]
}
```

## Per-Concept Requirements
- Exactly 6 questions per concept.
- Use this exact sequence:
1. `definition`
2. `identification`
3. `trap`
4. `application`
5. `comparison`
6. `reasoning`
- At least 2 of the 6 questions must be `msq`.
- Difficulty split per concept:
- 2 `easy`
- 2 `medium`
- 2 `hard`
- Default mapping:
- `definition` -> `easy`
- `identification` -> `easy`
- `trap` -> `medium`
- `comparison` -> `medium`
- `application` -> `hard`
- `reasoning` -> `hard`

## Answer Rules
- `answer` must always be an array of option labels.
- For `mcq`, include exactly 1 label.
- For `msq`, include at least 2 labels.
- Labels must only be `A`, `B`, `C`, `D`.
- The answer labels must match the correct options exactly.

## Option Rules
- Every question must have exactly 4 options: `A`, `B`, `C`, `D`.
- Options should be similar in length, structure, and detail.
- Correct options must not stand out by wording or specificity.
- Distractors must be plausible and tied to common misconceptions.
- Do not use "all of the above" or "none of the above".

## Question-Type Guidance
- Trap questions should target believable conceptual errors, not language tricks.
- Application questions should use concrete situations.
- Comparison questions should test real conceptual distinction.
- Reasoning questions should include causal and near-miss options.
- Use `image` only when a provided diagram is necessary; otherwise use `null`.

## Validation
Before finalizing, ensure:
- every concept has exactly 6 questions
- every question has non-empty text
- every question has valid `question_format`, `difficulty`, and `type`
- every option has non-empty text
- all IDs are unique
- no duplicate question intent exists
- every claim is supported by the source content
- `image` is `null` or a valid provided filename

## ID Format
Use: `CH<chapter_number>_C<concept_index>_Q<question_index>`

Examples:
- `CH10_C1_Q1`
- `CH10_C1_Q2`
- `CH10_C2_Q1`

## Final Constraint
- Output only the final JSON.
- No markdown fences.
- No commentary.
- No trailing explanation.
