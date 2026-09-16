"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";

import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from "@/components/ui/combobox";
import { getSkill, listSkills } from "@/lib/api";

/**
 * Pick a registered skill, then one of its versions.
 *
 * A picker rather than two free text fields, because a name lookup can only
 * ever answer for a name the registry holds: typing one it does not is a
 * guaranteed 404. The list is `GET /skills`, which hides test namespaces, so
 * what is offered is what the registry page shows.
 *
 * Versions come from the chosen skill's own detail read, newest first. A skill
 * with exactly one version fills it in, since there is nothing to choose.
 */

/** The registry holds a few dozen skills; one page of the API's maximum covers it. */
const LIST_LIMIT = 100;

const FIELD = "h-11 [&_input]:px-4 [&_input]:font-mono [&_input]:text-sm";

export function SkillVersionPicker({
  skillId,
  version,
  onSkillChange,
  onVersionChange,
  disabled,
}: {
  skillId: string | null;
  version: string | null;
  onSkillChange: (next: string | null) => void;
  onVersionChange: (next: string | null) => void;
  disabled?: boolean;
}) {
  const skills = useQuery({
    queryKey: ["check-skill-options", LIST_LIMIT],
    queryFn: () => listSkills({ start: 0, limit: LIST_LIMIT }),
  });

  const detail = useQuery({
    queryKey: ["check-skill-versions", skillId],
    queryFn: () => getSkill(skillId as string),
    enabled: skillId !== null,
  });

  const skillIds = useMemo(
    () => skills.data?.skills.map((s) => s.skill_id) ?? [],
    [skills.data],
  );
  // Registration order runs oldest to newest; the newest is what people want.
  // Only a version list for the skill currently chosen counts: a cached read
  // for the previous skill must not autofill a version it does not have.
  const versions = useMemo(
    () =>
      detail.data && detail.data.skill_id === skillId
        ? [...detail.data.versions].reverse()
        : [],
    [detail.data, skillId],
  );

  useEffect(() => {
    if (versions.length === 1 && version !== versions[0]) {
      onVersionChange(versions[0]);
    }
  }, [versions, version, onVersionChange]);

  const skillPlaceholder = skills.isPending
    ? "Loading the registry..."
    : skills.error
      ? "Could not load the registry"
      : "Search registered skills";

  const versionPlaceholder =
    skillId === null
      ? "Choose a skill first"
      : detail.isPending
        ? "Loading versions..."
        : detail.error
          ? "Could not load versions"
          : "Choose a version";

  return (
    <div className="grid gap-5 sm:grid-cols-[1fr_16rem]">
      <div>
        <label htmlFor="check-skill-id" className="text-xs text-text-tertiary">
          Skill id
        </label>
        <Combobox
          items={skillIds}
          value={skillId}
          onValueChange={(next) => {
            onSkillChange(next);
            onVersionChange(null);
          }}
          autoHighlight
          disabled={disabled || skills.isPending || Boolean(skills.error)}
        >
          <ComboboxInput
            id="check-skill-id"
            placeholder={skillPlaceholder}
            className={`mt-2 w-full ${FIELD}`}
            showClear={skillId !== null}
          />
          <ComboboxContent>
            <ComboboxEmpty>No registered skill matches</ComboboxEmpty>
            <ComboboxList>
              {(item: string) => (
                <ComboboxItem
                  key={item}
                  value={item}
                  className="py-2 pl-3 font-mono text-sm"
                >
                  {item}
                </ComboboxItem>
              )}
            </ComboboxList>
          </ComboboxContent>
        </Combobox>
        {skills.data && skills.data.skills.length < skills.data.total ? (
          <p className="mt-2 text-xs text-text-tertiary">
            Showing the first {skills.data.skills.length} of{" "}
            {skills.data.total} skills.
          </p>
        ) : null}
      </div>

      <div>
        <label htmlFor="check-version" className="text-xs text-text-tertiary">
          Version
          {versions.length === 1 ? (
            <span className="ml-1.5">(the only one registered)</span>
          ) : null}
        </label>
        <Combobox
          items={versions}
          value={version}
          onValueChange={onVersionChange}
          autoHighlight
          disabled={disabled || skillId === null || versions.length === 0}
        >
          <ComboboxInput
            id="check-version"
            placeholder={versionPlaceholder}
            className={`mt-2 w-full ${FIELD}`}
          />
          <ComboboxContent>
            <ComboboxEmpty>No version matches</ComboboxEmpty>
            <ComboboxList>
              {(item: string) => (
                <ComboboxItem
                  key={item}
                  value={item}
                  className="py-2 pl-3 font-mono text-sm"
                >
                  {item}
                </ComboboxItem>
              )}
            </ComboboxList>
          </ComboboxContent>
        </Combobox>
      </div>
    </div>
  );
}
