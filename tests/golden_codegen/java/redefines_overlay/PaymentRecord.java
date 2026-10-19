import java.math.BigDecimal;

public class PaymentRecord {
    private String paymentType;
    private BigDecimal paymentAmount;
    private CardData cardData;
    private CheckData checkData;  // REDEFINES CARD-DATA
    public String getPaymentType() { return paymentType; }
    public void setPaymentType(String paymentType) { this.paymentType = paymentType; }
    public BigDecimal getPaymentAmount() { return paymentAmount; }
    public void setPaymentAmount(BigDecimal paymentAmount) { this.paymentAmount = paymentAmount; }
    public CardData getCardData() { return cardData; }
    public void setCardData(CardData cardData) { this.cardData = cardData; }
    public CheckData getCheckData() { return checkData; }
    public void setCheckData(CheckData checkData) { this.checkData = checkData; }

    public static class CardData {
        private String cardNumber;
        private short cardExp;
        public String getCardNumber() { return cardNumber; }
        public void setCardNumber(String cardNumber) { this.cardNumber = cardNumber; }
        public short getCardExp() { return cardExp; }
        public void setCardExp(short cardExp) { this.cardExp = cardExp; }
    }

    public static class CheckData {
        private long checkNumber;
        private int bankRouting;
        public long getCheckNumber() { return checkNumber; }
        public void setCheckNumber(long checkNumber) { this.checkNumber = checkNumber; }
        public int getBankRouting() { return bankRouting; }
        public void setBankRouting(int bankRouting) { this.bankRouting = bankRouting; }
    }

    public static void validateCardExp(short v) {
        if (v < 0 || v > 9999) {
            throw new IllegalArgumentException("CARD-EXP: " + v + " outside 0..9999");
        }
    }

    public static void validateCheckNumber(long v) {
        if (v < 0L || v > 9999999999L) {
            throw new IllegalArgumentException("CHECK-NUMBER: " + v + " outside 0..9999999999");
        }
    }

    public static void validateBankRouting(int v) {
        if (v < 0 || v > 999999999) {
            throw new IllegalArgumentException("BANK-ROUTING: " + v + " outside 0..999999999");
        }
    }
}
