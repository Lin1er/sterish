import Link from "next/link";

/**
 * An unregistered skill.
 *
 * The wording matters more than it looks. A miss means the registry has never
 * heard of this id, which is not the same as "no problems found" and must never
 * read that way. Spec design rule 3: a miss is a 404, never a fabricated
 * "unknown but probably fine".
 */
export default function NotFound() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-24 text-center sm:px-6">
      <h2 className="text-2xl font-bold">This skill is not registered</h2>
      <p className="mx-auto mt-3 text-sm text-text-secondary">
        The registry has no entry under that id. That is not a verdict and not a
        clean bill of health, it is the absence of any record at all. Nothing
        here has been audited, because there is nothing here.
      </p>
      <Link
        href="/"
        className="mt-6 inline-block text-sm text-keyword hover:underline"
      >
        Back to the registry
      </Link>
    </div>
  );
}
