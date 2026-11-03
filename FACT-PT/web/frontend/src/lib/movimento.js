/** Shared framer-motion transitions, so every part of the page moves the same way. */

export const SUAVE = [0.2, 0.7, 0.3, 1];

/** A section of the result arriving, slower than `SURGIR`: sections come one at a time while the
    run goes on, and each is given the time to be seen arriving. */
export const APARECER = {
  initial: { opacity: 0, y: 28 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: 10, transition: { duration: 0.3, ease: SUAVE } },
  transition: { duration: 0.9, ease: SUAVE },
};

/** A block arriving on the page: rises a little and fades in. */
export const SURGIR = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: 10 },
  transition: { duration: 0.34, ease: SUAVE },
};
