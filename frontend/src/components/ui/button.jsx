import { buttonVariants } from '@/components/ui/button-variants'
import { cn } from '@/lib/utils'

export function Button({ className, variant, size, type = 'button', ...props }) {
  return (
    <button
      type={type}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  )
}
