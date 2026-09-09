/**
 * GitHub and X marks as inline SVG.
 *
 * lucide-react dropped its brand icons, so `Github` and `Twitter` no longer
 * exist in the package and the `X` it does export is the close cross, not the
 * logo. These are the official marks, drawn at 24 and scaled by font size like
 * every other icon here.
 */

type IconProps = { className?: string };

export function GithubIcon({ className }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden
      className={className}
    >
      <path d="M12 .5C5.37.5 0 5.87 0 12.5c0 5.3 3.44 9.8 8.21 11.39.6.11.82-.26.82-.58 0-.29-.01-1.24-.02-2.25-3.34.73-4.04-1.42-4.04-1.42-.55-1.39-1.34-1.76-1.34-1.76-1.09-.75.08-.73.08-.73 1.21.09 1.84 1.24 1.84 1.24 1.07 1.84 2.81 1.31 3.5 1 .11-.78.42-1.31.76-1.61-2.67-.3-5.47-1.34-5.47-5.96 0-1.32.47-2.39 1.24-3.23-.12-.31-.54-1.53.12-3.18 0 0 1.01-.32 3.3 1.23a11.5 11.5 0 0 1 6.01 0c2.29-1.55 3.3-1.23 3.3-1.23.66 1.65.24 2.87.12 3.18.77.84 1.24 1.91 1.24 3.23 0 4.63-2.81 5.65-5.49 5.95.43.37.82 1.1.82 2.22 0 1.6-.02 2.89-.02 3.29 0 .32.22.7.83.58A12 12 0 0 0 24 12.5C24 5.87 18.63.5 12 .5z" />
    </svg>
  );
}

export function XIcon({ className }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden
      className={className}
    >
      <path d="M18.9 1.9h3.68l-8.04 9.19L24 22.1h-7.4l-5.8-7.58-6.64 7.58H.48l8.6-9.83L0 1.9h7.59l5.24 6.93L18.9 1.9zm-1.29 18h2.04L6.49 3.99H4.3l13.31 15.91z" />
    </svg>
  );
}
