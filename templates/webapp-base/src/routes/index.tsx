import { createFileRoute } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export const Route = createFileRoute("/")({
  component: Index,
});

// Default starter route. The Build agent replaces/extends this when designing
// an app. It uses only design tokens (bg-background, text-foreground, etc.)
// and shadcn primitives so a token reskin restyles it automatically.
function Index() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Your app starts here</CardTitle>
          <CardDescription>
            Scaffolded from the base template. Describe what to build and the
            agent will design on top of this — retheming tokens and composing
            components.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button className="w-full">Get started</Button>
        </CardContent>
      </Card>
    </main>
  );
}
