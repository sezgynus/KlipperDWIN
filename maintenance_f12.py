"""Pure bounded five-level adaptive F12 startup-threshold search.

No I/O, fan actuation, or inferred physical evidence. Each operator reply
must refer to five independently observed start-from-rest attempts.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class F12Bracket:
    low: int = 0
    high: int = 255
    stage: int = 0
    last_levels: tuple = ()
    last_failure: int = 0
    first_success: int | None = None

    def levels(self):
        if self.high <= self.low or not 0 <= self.low <= self.high <= 255:
            raise ValueError('invalid_f12_bracket')
        if self.high-self.low <= 2:
            return ()
        # At 8-bit resolution fewer than five distinct commands remain.
        # Never invent duplicated PWM stages merely to fill the menu.
        count = min(5,self.high-self.low)
        return tuple(self.low + (self.high-self.low)*i//count
                     for i in range(1,count+1))

    def next(self, first_moving):
        """first_moving: 1..5; 0 means none started.

        Never widen a previously proven failure/success bracket.
        """
        levels = self.levels()
        if not levels or type(first_moving) is not int or not 0 <= first_moving <= 5:
            raise ValueError('invalid_f12_observation')
        if first_moving == 0:
            # None means none at the highest attempted value. If an earlier
            # success bound already exists, this is contradictory evidence.
            if self.first_success is not None:
                raise ValueError('contradictory_f12_observation')
            if self.high == 255:
                return F12Bracket(255,255,self.stage+1,levels,255,None)
            return F12Bracket(self.high,255,self.stage+1,levels,self.high,None)
        success = levels[first_moving-1]
        failure = self.low if first_moving == 1 else levels[first_moving-2]
        if self.first_success is not None and success > self.first_success:
            raise ValueError('contradictory_f12_observation')
        lo=max(self.last_failure,failure)
        hi=min(self.first_success if self.first_success is not None else 255,success)
        if lo>=hi:
            raise ValueError('contradictory_f12_observation')
        return F12Bracket(lo,hi,self.stage+1,levels,lo,hi)

    @property
    def resolved(self):
        return self.first_success is not None and self.high-self.low <= 2
