      *> CHECK-DATA overlays the same bytes as CARD-DATA (REDEFINES).
       01  PAYMENT-RECORD.
           05  PAYMENT-TYPE        PIC X(1).
           05  PAYMENT-AMOUNT      PIC S9(7)V99.
           05  CARD-DATA.
               10  CARD-NUMBER     PIC X(16).
               10  CARD-EXP        PIC 9(4).
           05  CHECK-DATA REDEFINES CARD-DATA.
               10  CHECK-NUMBER    PIC 9(10).
               10  BANK-ROUTING    PIC 9(9).
