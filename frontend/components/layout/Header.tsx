"use client";

import { useRouter } from "next/navigation";
import { logout, type User } from "@/lib/api";
import { avatarUrl, displayName, initials } from "@/lib/user";
import Logo from "./Logo";

type HeaderProps = {
  email: string | null;
  user?: User | null;
  variant?: "dashboard" | "scan";
  actions?: React.ReactNode;
};

export default function Header({ email, user, actions }: HeaderProps) {
  const router = useRouter();

  // Fall back to a minimal user object when only email was passed so we still
  // render a proper avatar + name for pages that haven't been updated to pass
  // the full user object.
  const resolvedUser =
    user ?? (email ? ({ id: 0, email } as User) : null);
  const name = resolvedUser ? displayName(resolvedUser) : null;
  const avatar = resolvedUser ? avatarUrl(resolvedUser) : null;
  const monogram = resolvedUser ? initials(resolvedUser) : "";

  return (
    <header className="sticky top-0 z-10 border-b border-border bg-header-bg">
      <div className="mx-auto flex h-12 max-w-7xl items-center justify-between gap-4 px-4 lg:px-8">
        <div className="flex min-w-0 items-center gap-4">
          <Logo />
        </div>

        <div className="flex shrink-0 items-center gap-3">
          {actions}
          {resolvedUser && (
            <>
              <div
                className="flex items-center gap-2"
                title={resolvedUser.email}
              >
                {avatar ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={avatar}
                    alt=""
                    width={22}
                    height={22}
                    className="size-[22px] rounded-[3px] border border-border object-cover"
                  />
                ) : (
                  <span
                    aria-hidden
                    className="inline-flex size-[22px] items-center justify-center rounded-[3px] border border-accent/25 bg-accent-subtle text-[11px] font-semibold text-accent"
                  >
                    {monogram}
                  </span>
                )}
                <span className="hidden max-w-[160px] truncate text-[13px] font-medium text-text-primary sm:inline">
                  {name}
                </span>
              </div>
              <span aria-hidden className="hidden h-4 w-px bg-border sm:inline-block" />
              <button
                type="button"
                onClick={() => void logout().then(() => router.push("/login"))}
                className="text-[12px] font-medium text-text-secondary hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring rounded-sm"
              >
                Sign out
              </button>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
