using System;

namespace Unimarketing.UnimailApiSdk.CSharp.Model
{
    /// <summary>
    ///     公司账户
    /// </summary>
    public class Account : BaseModel
    {
        public long CompanyId { get; set; }

        public string CompanyName { get; set; }

        public string CompanyDesc { get; set; }

        public string Email { get; set; }

        public string Tel { get; set; }

        public string Fax { get; set; }

        /// <summary>
        ///     邮编
        /// </summary>
        public string PostCode { get; set; }

        public string CompanyAddress { get; set; }

        /// <summary>
        ///     注册日期
        /// </summary>
        public DateTime? StartTime { get; set; }

        /// <summary>
        ///     到期日
        /// </summary>
        public DateTime? EndTime { get; set; }

        public DateTime? UpdateTime { get; set; }

        /// <summary>
        ///     剩余天数
        /// </summary>
        public int? ResidueDay { get; set; }

        /// <summary>
        ///     联系人总数
        /// </summary>
        public int? ContactQuota { get; set; }

        /// <summary>
        ///     剩余联系人数
        /// </summary>
        public int? ContactAvail { get; set; }

        /// <summary>
        ///     邮件总数
        /// </summary>
        public int? MailQuota { get; set; }

        /// <summary>
        ///     剩余邮件数
        /// </summary>
        public int? MailAvail { get; set; }

        /// <summary>
        ///     空间总数
        /// </summary>
        public int? CapacityQuota { get; set; }

        /// <summary>
        ///     剩余空间数(M)
        /// </summary>
        public double? CapacityAvail { get; set; }

        public override string ToString()
        {
            return "Id=" + Id + ",CompanyId=" + CompanyId + ",CompanyName=" + CompanyName
                   + ",CompanyDesc=" + CompanyDesc
                   + ",Email=" + Email
                   + ",Tel=" + Tel
                   + ",Fax=" + Fax
                   + ",PostCode=" + PostCode
                   + ",CompanyAddress=" + CompanyAddress
                   + ",StartTime=" + StartTime
                   + ",EndTime=" + EndTime
                   + ",UpdateTime=" + UpdateTime
                   + ",ResidueDay=" + ResidueDay
                   + ",ContactQuota=" + ContactQuota
                   + ",ContactAvail=" + ContactAvail
                   + ",MailQuota=" + MailQuota
                   + ",MailAvail=" + MailAvail
                   + ",CapacityQuota=" + CapacityQuota
                   + ",CapacityAvail=" + CapacityAvail;
        }
    }
}