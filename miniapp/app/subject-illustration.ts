export type SubjectIconKind =
  | "biology"
  | "chemistry"
  | "english"
  | "history"
  | "informatics"
  | "literature"
  | "mathematics"
  | "physics"
  | "russian"
  | "social"
  | "general";

const SUBJECT_ICONS: Record<string, SubjectIconKind> = {
  "английский язык": "english",
  биология: "biology",
  история: "history",
  информатика: "informatics",
  литература: "literature",
  математика: "mathematics",
  обществознание: "social",
  русский: "russian",
  "русский язык": "russian",
  физика: "physics",
  химия: "chemistry",
};

export function subjectIconKind(subject: string): SubjectIconKind {
  return SUBJECT_ICONS[subject.trim().toLocaleLowerCase("ru-RU")] ?? "general";
}
